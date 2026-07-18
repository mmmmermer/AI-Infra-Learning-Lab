from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from .corpus import Document
from .ingestion import TrustedCollectionPolicy
from .retrieval import build_chunks
from .security import InsufficientScope, Principal, require_scope
from .service import RagQueryRequest, RetrievalCache, ServiceResult, execute_retrieval


SUPPORTED_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})


class LifecycleStatus(StrEnum):
    ACCEPTED = "accepted"
    UPDATED = "updated"
    REJECTED_CORRUPT = "rejected_corrupt"
    REJECTED_BLANK = "rejected_blank"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_VERSION_CONFLICT = "rejected_version_conflict"
    REJECTED_UNSUPPORTED_MEDIA = "rejected_unsupported_media"
    DELETED = "deleted"
    DELETE_NOT_FOUND = "delete_not_found"
    EXPIRED = "expired"


@dataclass(frozen=True)
class SourceRecord:
    document_id: str
    content: bytes
    media_type: str
    source_version: int
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id must not be empty")
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")
        if not self.media_type.strip():
            raise ValueError("media_type must not be empty")
        if (
            isinstance(self.source_version, bool)
            or not isinstance(self.source_version, int)
            or self.source_version < 1
        ):
            raise ValueError("source_version must be a positive integer")


@dataclass(frozen=True)
class LifecycleOutcome:
    document_id: str
    source_version: int
    status: LifecycleStatus
    collection_version: str
    detail_code: str


class LifecycleIndex:
    """A deterministic in-memory lifecycle boundary, not a production index."""

    def __init__(
        self,
        policy: TrustedCollectionPolicy,
        cache: RetrievalCache | None = None,
    ) -> None:
        self.policy = policy
        self.cache = cache or RetrievalCache()
        self._documents: dict[str, Document] = {}
        self._expires_at: dict[str, datetime | None] = {}
        self._latest_versions: dict[str, int] = {}
        self._content_owners: dict[str, str] = {}
        self._generation = 0

    @property
    def collection_version(self) -> str:
        return f"lifecycle-{self._generation:06d}"

    @property
    def documents(self) -> tuple[Document, ...]:
        return tuple(
            self._documents[key] for key in sorted(self._documents)
        )

    def ingest(
        self,
        record: SourceRecord,
        principal: Principal | None,
        *,
        observed_at: datetime,
    ) -> LifecycleOutcome:
        self._verify_principal(principal, "rag:ingest")
        self._require_aware(observed_at)
        if record.expires_at is not None:
            self._require_aware(record.expires_at)
        if record.media_type not in SUPPORTED_MEDIA_TYPES:
            return self._outcome(
                record, LifecycleStatus.REJECTED_UNSUPPORTED_MEDIA, "unsupported_media_type"
            )
        try:
            text = record.content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return self._outcome(
                record, LifecycleStatus.REJECTED_CORRUPT, "invalid_utf8"
            )
        text = text.strip()
        if not text:
            return self._outcome(record, LifecycleStatus.REJECTED_BLANK, "blank_after_parse")
        if record.expires_at is not None and record.expires_at <= observed_at:
            return self._outcome(
                record, LifecycleStatus.REJECTED_EXPIRED, "expired_before_ingestion"
            )

        content_hash = sha256(text.encode("utf-8")).hexdigest()
        duplicate_owner = self._content_owners.get(content_hash)
        if duplicate_owner is not None:
            return self._outcome(
                record,
                LifecycleStatus.REJECTED_DUPLICATE,
                "duplicate_content",
            )

        latest_version = self._latest_versions.get(record.document_id)
        if latest_version is not None and record.source_version <= latest_version:
            return self._outcome(
                record,
                LifecycleStatus.REJECTED_VERSION_CONFLICT,
                "source_version_not_monotonic",
            )

        previous = self._documents.get(record.document_id)
        if previous is not None:
            self._content_owners.pop(previous.content_sha256, None)
        document = Document(
            document_id=record.document_id,
            permission_group=self.policy.permission_group,
            text=text,
            tenant_id=self.policy.tenant_id,
            collection_id=self.policy.collection_id,
            source_id=self.policy.source_id,
            source_version=str(record.source_version),
        )
        self._documents[record.document_id] = document
        self._expires_at[record.document_id] = record.expires_at
        self._latest_versions[record.document_id] = record.source_version
        self._content_owners[content_hash] = record.document_id
        self._advance_generation()
        status = LifecycleStatus.UPDATED if previous is not None else LifecycleStatus.ACCEPTED
        return self._outcome(record, status, status.value)

    def delete(
        self,
        document_id: str,
        source_version: int,
        principal: Principal | None,
    ) -> LifecycleOutcome:
        self._verify_principal(principal, "rag:delete")
        latest_version = self._latest_versions.get(document_id)
        synthetic = SourceRecord(document_id, b"", "text/plain", source_version)
        if latest_version is not None and source_version <= latest_version:
            return self._outcome(
                synthetic,
                LifecycleStatus.REJECTED_VERSION_CONFLICT,
                "delete_version_not_monotonic",
            )
        document = self._documents.pop(document_id, None)
        if document is None:
            self._latest_versions[document_id] = source_version
            self._advance_generation()
            return self._outcome(
                synthetic,
                LifecycleStatus.DELETE_NOT_FOUND,
                "tombstone_recorded_without_active_document",
            )
        self._content_owners.pop(document.content_sha256, None)
        self._expires_at.pop(document_id, None)
        self._latest_versions[document_id] = source_version
        self._advance_generation()
        return self._outcome(synthetic, LifecycleStatus.DELETED, "tombstone_recorded")

    def expire_documents(self, *, observed_at: datetime) -> tuple[LifecycleOutcome, ...]:
        self._require_aware(observed_at)
        expired_ids = [
            document_id
            for document_id, expires_at in self._expires_at.items()
            if expires_at is not None and expires_at <= observed_at
        ]
        outcomes: list[LifecycleOutcome] = []
        for document_id in sorted(expired_ids):
            document = self._documents.pop(document_id)
            self._content_owners.pop(document.content_sha256, None)
            self._expires_at.pop(document_id, None)
            version = self._latest_versions[document_id]
            self._advance_generation()
            outcomes.append(
                LifecycleOutcome(
                    document_id=document_id,
                    source_version=version,
                    status=LifecycleStatus.EXPIRED,
                    collection_version=self.collection_version,
                    detail_code="retention_expired",
                )
            )
        return tuple(outcomes)

    def query(
        self,
        request: RagQueryRequest,
        principal: Principal | None,
        *,
        observed_at: datetime,
        chunk_size: int = 80,
        overlap: int = 10,
    ) -> ServiceResult:
        verified = self._verify_principal(principal, "rag:query")
        self.expire_documents(observed_at=observed_at)
        return execute_retrieval(
            request,
            verified,
            build_chunks(list(self.documents), chunk_size=chunk_size, overlap=overlap),
            self.cache,
            collection_version=self.collection_version,
        )

    def _verify_principal(self, principal: Principal | None, scope: str) -> Principal:
        verified = require_scope(principal, scope)
        if verified.tenant_id != self.policy.tenant_id:
            raise InsufficientScope("lifecycle_policy_tenant_mismatch")
        return verified

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lifecycle timestamps must be timezone-aware")

    def _advance_generation(self) -> None:
        self._generation += 1
        self.cache.invalidate_collection(
            self.policy.tenant_id, self.policy.collection_id
        )

    def _outcome(
        self,
        record: SourceRecord,
        status: LifecycleStatus,
        detail_code: str,
    ) -> LifecycleOutcome:
        return LifecycleOutcome(
            document_id=record.document_id,
            source_version=record.source_version,
            status=status,
            collection_version=self.collection_version,
            detail_code=detail_code,
        )
