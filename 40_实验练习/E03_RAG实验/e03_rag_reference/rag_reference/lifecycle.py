from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import wraps
from hashlib import sha256
import json
from threading import RLock
from typing import Any, TypeVar, cast

from .corpus import Document
from .ingestion import TrustedCollectionPolicy
from .parsing import (
    ExtractionAdapter,
    ParseLimits,
    ParseQualityReport,
    ParseStatus,
    parse_source,
)
from .retrieval import build_chunks
from .security import InsufficientScope, Principal, require_scope
from .service import RagQueryRequest, RetrievalCache, ServiceResult, execute_retrieval


_F = TypeVar("_F", bound=Callable[..., Any])


def _serialized_state(method: _F) -> _F:
    """Serialize one public operation against the in-memory lifecycle state."""

    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._state_lock:
            return method(self, *args, **kwargs)

    return cast(_F, wrapped)


class LifecycleStatus(StrEnum):
    ACCEPTED = "accepted"
    UPDATED = "updated"
    REJECTED_ADAPTER_FAILURE = "rejected_adapter_failure"
    REJECTED_ADAPTER_REQUIRED = "rejected_adapter_required"
    REJECTED_BLANK = "rejected_blank"
    REJECTED_CORRUPT = "rejected_corrupt"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_DELETE_PENDING = "rejected_delete_pending"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_OCR_REQUIRED = "rejected_ocr_required"
    REJECTED_RESOURCE_LIMIT = "rejected_resource_limit"
    REJECTED_VERSION_CONFLICT = "rejected_version_conflict"
    REJECTED_UNSUPPORTED_MEDIA = "rejected_unsupported_media"
    DELETE_PENDING = "delete_pending"
    DELETED = "deleted"
    DELETE_NOT_FOUND = "delete_not_found"
    EXPIRED = "expired"


class ArtifactKind(StrEnum):
    RAW = "raw"
    PARSED = "parsed"
    CHUNK = "chunk"
    VECTOR = "vector"
    CACHE = "cache"
    PROMPT = "prompt"
    OUTPUT = "output"
    CITATION = "citation"


CASCADE_ORDER = tuple(ArtifactKind)


@dataclass(frozen=True)
class SourceRecord:
    document_id: str
    content: bytes = field(repr=False)
    media_type: str
    source_version: int
    expires_at: datetime | None = None
    source_locator: str = field(default="", repr=False)
    expected_markers: tuple[str, ...] = field(default=(), repr=False)

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
        if not isinstance(self.source_locator, str):
            raise TypeError("source_locator must be str")
        if not isinstance(self.expected_markers, tuple) or any(
            not isinstance(marker, str) or not marker
            for marker in self.expected_markers
        ):
            raise ValueError(
                "expected_markers must be a tuple of non-empty strings"
            )


@dataclass(frozen=True)
class LifecycleOutcome:
    document_id: str
    source_version: int
    status: LifecycleStatus
    collection_version: str
    detail_code: str
    parse_report: ParseQualityReport | None = None


@dataclass(frozen=True)
class ArtifactInventoryEntry:
    artifact_kind: ArtifactKind
    active_count: int
    artifact_fingerprints: tuple[str, ...]
    parent_fingerprints: tuple[str, ...]

    def to_audit_dict(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind.value,
            "active_count": self.active_count,
            "artifact_fingerprints": list(self.artifact_fingerprints),
            "parent_fingerprints": list(self.parent_fingerprints),
        }


@dataclass(frozen=True)
class ArtifactInvalidation:
    artifact_kind: ArtifactKind
    invalidated_count: int
    artifact_fingerprints: tuple[str, ...]

    def to_audit_dict(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind.value,
            "invalidated_count": self.invalidated_count,
            "artifact_fingerprints": list(self.artifact_fingerprints),
        }


@dataclass(frozen=True)
class DeletionReceipt:
    operation_fingerprint: str
    document_fingerprint: str
    source_version: int
    status: LifecycleStatus
    detail_code: str
    collection_version: str
    invalidations: tuple[ArtifactInvalidation, ...]
    reference_payload_copies_remaining: int
    tombstone_retained: bool
    retryable: bool
    external_physical_erasure_verified: bool = False
    boundary_code: str = "external_storage_and_backup_erasure_not_verified"

    def to_audit_dict(self) -> dict[str, object]:
        """Return a content-free receipt suitable for structured audit logs."""

        return {
            "operation_fingerprint": self.operation_fingerprint,
            "document_fingerprint": self.document_fingerprint,
            "source_version": self.source_version,
            "status": self.status.value,
            "detail_code": self.detail_code,
            "collection_version": self.collection_version,
            "invalidations": [
                item.to_audit_dict() for item in self.invalidations
            ],
            "reference_payload_copies_remaining": (
                self.reference_payload_copies_remaining
            ),
            "tombstone_retained": self.tombstone_retained,
            "retryable": self.retryable,
            "external_physical_erasure_verified": (
                self.external_physical_erasure_verified
            ),
            "boundary_code": self.boundary_code,
        }


@dataclass(frozen=True)
class DeletionResult:
    outcome: LifecycleOutcome
    receipt: DeletionReceipt


@dataclass(frozen=True)
class _ArtifactCopy:
    payload: bytes = field(repr=False)
    parent_fingerprints: tuple[str, ...]


@dataclass
class _DeletionState:
    source_version: int
    missing_at_start: bool
    collection_version: str
    next_cascade_index: int = 0
    invalidated_fingerprints: dict[ArtifactKind, set[str]] = field(
        default_factory=lambda: {kind: set() for kind in CASCADE_ORDER}
    )
    completed: bool = False
    detail_code: str = "cascade_pending"


_PARSE_STATUS_MAP = {
    ParseStatus.REJECTED_ADAPTER_FAILURE: LifecycleStatus.REJECTED_ADAPTER_FAILURE,
    ParseStatus.REJECTED_ADAPTER_REQUIRED: LifecycleStatus.REJECTED_ADAPTER_REQUIRED,
    ParseStatus.REJECTED_BLANK: LifecycleStatus.REJECTED_BLANK,
    ParseStatus.REJECTED_CORRUPT: LifecycleStatus.REJECTED_CORRUPT,
    ParseStatus.REJECTED_OCR_REQUIRED: LifecycleStatus.REJECTED_OCR_REQUIRED,
    ParseStatus.REJECTED_RESOURCE_LIMIT: LifecycleStatus.REJECTED_RESOURCE_LIMIT,
    ParseStatus.REJECTED_UNSUPPORTED_MEDIA: (
        LifecycleStatus.REJECTED_UNSUPPORTED_MEDIA
    ),
}

_DERIVED_ARTIFACTS = frozenset(
    {
        ArtifactKind.VECTOR,
        ArtifactKind.PROMPT,
        ArtifactKind.OUTPUT,
        ArtifactKind.CITATION,
    }
)


class LifecycleIndex:
    """A deterministic in-memory lifecycle boundary, not a production index."""

    def __init__(
        self,
        policy: TrustedCollectionPolicy,
        cache: RetrievalCache | None = None,
        *,
        parser_adapters: Mapping[str, ExtractionAdapter] | None = None,
        parse_limits: ParseLimits | None = None,
    ) -> None:
        self.policy = policy
        self.cache = cache or RetrievalCache()
        self.parser_adapters = dict(parser_adapters or {})
        self.parse_limits = parse_limits or ParseLimits()
        self._state_lock = RLock()
        self._documents: dict[str, Document] = {}
        self._expires_at: dict[str, datetime | None] = {}
        self._latest_versions: dict[str, int] = {}
        self._content_owners: dict[str, str] = {}
        self._artifacts: dict[
            str, dict[ArtifactKind, dict[str, _ArtifactCopy]]
        ] = {}
        self._deletions: dict[str, _DeletionState] = {}
        self._retention_watermark: datetime | None = None
        self._generation = 0

    @property
    @_serialized_state
    def collection_version(self) -> str:
        return f"lifecycle-{self._generation:06d}"

    @_serialized_state
    def active_documents(
        self, principal: Principal | None
    ) -> tuple[Document, ...]:
        self._verify_policy_access(principal, "rag:query")
        return tuple(self._documents[key] for key in sorted(self._documents))

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

        with self._state_lock:
            if self._record_is_expired(record, observed_at):
                return self._outcome(
                    record,
                    LifecycleStatus.REJECTED_EXPIRED,
                    "expired_before_ingestion",
                )
            conflict = self._ingest_state_conflict(record)
            if conflict is not None:
                return conflict
        parsed = parse_source(
            record.content,
            record.media_type,
            adapters=self.parser_adapters,
            limits=self.parse_limits,
            source_version=str(record.source_version),
            source_locator=record.source_locator or record.document_id,
            expected_markers=record.expected_markers,
        )
        if not parsed.accepted:
            status = _PARSE_STATUS_MAP[parsed.report.status]
            with self._state_lock:
                return self._outcome(
                    record,
                    status,
                    parsed.report.detail_code,
                    parsed.report,
                )

        content_hash = sha256(parsed.text.encode("utf-8")).hexdigest()
        with self._state_lock:
            # Parsing may invoke a slow external adapter. Recheck the monotonic
            # state and retention watermark so concurrent lifecycle events win.
            if self._record_is_expired(record, observed_at):
                return self._outcome(
                    record,
                    LifecycleStatus.REJECTED_EXPIRED,
                    "expired_before_commit",
                    parsed.report,
                )
            conflict = self._ingest_state_conflict(record)
            if conflict is not None:
                return conflict
            duplicate_owner = self._content_owners.get(content_hash)
            if (
                duplicate_owner is not None
                and duplicate_owner != record.document_id
            ):
                return self._outcome(
                    record,
                    LifecycleStatus.REJECTED_DUPLICATE,
                    "duplicate_content",
                    parsed.report,
                )

            previous = self._documents.get(record.document_id)
            if previous is not None:
                self._content_owners.pop(previous.content_sha256, None)
                self._discard_document_artifacts(record.document_id)
            document = Document(
                document_id=record.document_id,
                permission_group=self.policy.permission_group,
                text=parsed.text,
                tenant_id=self.policy.tenant_id,
                collection_id=self.policy.collection_id,
                source_id=self.policy.source_id,
                source_version=str(record.source_version),
            )
            self._documents[record.document_id] = document
            self._expires_at[record.document_id] = record.expires_at
            self._latest_versions[record.document_id] = record.source_version
            self._content_owners[content_hash] = record.document_id
            self._deletions.pop(record.document_id, None)
            self._record_ingested_artifacts(record, document)
            self._advance_generation()
            status = (
                LifecycleStatus.UPDATED
                if previous is not None
                else LifecycleStatus.ACCEPTED
            )
            return self._outcome(record, status, status.value, parsed.report)

    @_serialized_state
    def register_derived_artifact(
        self,
        document_id: str,
        artifact_kind: ArtifactKind,
        payload: bytes | str,
        principal: Principal | None,
        *,
        parent_fingerprints: tuple[str, ...],
    ) -> str:
        self._verify_principal(principal, "rag:ingest")
        if document_id not in self._documents:
            raise KeyError("document_not_active")
        if artifact_kind not in _DERIVED_ARTIFACTS:
            raise ValueError("artifact_kind_is_lifecycle_managed")
        if not parent_fingerprints:
            raise ValueError("lineage_parent_required")
        self._active_parent_kinds(document_id, parent_fingerprints)
        parent_kind_sequence = tuple(
            self._artifact_kind(document_id, fingerprint)
            for fingerprint in parent_fingerprints
        )
        allowed = {
            ArtifactKind.VECTOR: frozenset({ArtifactKind.PARSED}),
            ArtifactKind.PROMPT: frozenset(
                {ArtifactKind.CHUNK, ArtifactKind.CACHE}
            ),
            ArtifactKind.OUTPUT: frozenset({ArtifactKind.PROMPT}),
            ArtifactKind.CITATION: frozenset(
                {ArtifactKind.OUTPUT, ArtifactKind.CHUNK}
            ),
        }[artifact_kind]
        if not set(parent_kind_sequence).issubset(allowed):
            raise ValueError("lineage_parent_kind_mismatch")
        if artifact_kind in {ArtifactKind.VECTOR, ArtifactKind.OUTPUT} and len(
            parent_kind_sequence
        ) != 1:
            raise ValueError("lineage_parent_cardinality_mismatch")
        if artifact_kind == ArtifactKind.CITATION and (
            len(parent_kind_sequence) != 2
            or parent_kind_sequence.count(ArtifactKind.OUTPUT) != 1
            or parent_kind_sequence.count(ArtifactKind.CHUNK) != 1
        ):
            raise ValueError("lineage_parent_cardinality_mismatch")
        if artifact_kind == ArtifactKind.CITATION:
            output_parents = tuple(
                fingerprint
                for fingerprint in parent_fingerprints
                if self._artifact_kind(document_id, fingerprint)
                == ArtifactKind.OUTPUT
            )
            chunk_parents = tuple(
                fingerprint
                for fingerprint in parent_fingerprints
                if self._artifact_kind(document_id, fingerprint)
                == ArtifactKind.CHUNK
            )
            related = {
                (output_fingerprint, chunk_fingerprint)
                for output_fingerprint in output_parents
                for chunk_fingerprint in chunk_parents
                if self._lineage_has_ancestor(
                    document_id,
                    descendant_fingerprint=output_fingerprint,
                    ancestor_fingerprint=chunk_fingerprint,
                )
            }
            if related != {(output_parents[0], chunk_parents[0])}:
                raise ValueError("citation_chunk_not_in_output_lineage")
        return self._record_artifact(
            document_id,
            artifact_kind,
            payload,
            parent_fingerprints=parent_fingerprints,
        )

    @_serialized_state
    def artifact_inventory(
        self, document_id: str, principal: Principal | None
    ) -> tuple[ArtifactInventoryEntry, ...]:
        self._verify_policy_access(principal, "rag:query")
        stores = self._artifacts.get(document_id, {})
        entries: list[ArtifactInventoryEntry] = []
        for kind in CASCADE_ORDER:
            copies = stores.get(kind, {})
            parents = {
                parent
                for copy in copies.values()
                for parent in copy.parent_fingerprints
            }
            entries.append(
                ArtifactInventoryEntry(
                    artifact_kind=kind,
                    active_count=len(copies),
                    artifact_fingerprints=tuple(sorted(copies)),
                    parent_fingerprints=tuple(sorted(parents)),
                )
            )
        return tuple(entries)

    @_serialized_state
    def delete(
        self,
        document_id: str,
        source_version: int,
        principal: Principal | None,
    ) -> LifecycleOutcome:
        return self.delete_with_receipt(
            document_id, source_version, principal
        ).outcome

    @_serialized_state
    def delete_with_receipt(
        self,
        document_id: str,
        source_version: int,
        principal: Principal | None,
        *,
        fail_after: ArtifactKind | None = None,
    ) -> DeletionResult:
        self._verify_principal(principal, "rag:delete")
        if fail_after is not None and not isinstance(fail_after, ArtifactKind):
            raise TypeError("fail_after must be ArtifactKind or None")
        synthetic = SourceRecord(document_id, b"", "text/plain", source_version)
        existing_state = self._deletions.get(document_id)
        if existing_state is not None and existing_state.source_version == source_version:
            if existing_state.completed:
                return self._deletion_result(
                    synthetic, existing_state, "idempotent_delete_replay"
                )
            return self._resume_cascade(
                synthetic, existing_state, fail_after=fail_after
            )
        if existing_state is not None and not existing_state.completed:
            return self._pending_delete_conflict_result(synthetic)

        latest_version = self._latest_versions.get(document_id)
        if latest_version is not None and source_version <= latest_version:
            return self._version_conflict_result(synthetic)

        missing_at_start = (
            document_id not in self._documents
            and self._reference_payload_copy_count(document_id) == 0
        )

        # The monotonic tombstone and collection version commit before any
        # payload cleanup. A failed cascade therefore cannot make data queryable.
        self._latest_versions[document_id] = source_version
        self._generation += 1
        state = _DeletionState(
            source_version=source_version,
            missing_at_start=missing_at_start,
            collection_version=self.collection_version,
        )
        self._deletions[document_id] = state
        document = self._documents.pop(document_id, None)
        if document is not None:
            self._content_owners.pop(document.content_sha256, None)
        self._expires_at.pop(document_id, None)
        return self._resume_cascade(
            synthetic, state, fail_after=fail_after
        )

    @_serialized_state
    def expire_documents(
        self, principal: Principal | None, *, observed_at: datetime
    ) -> tuple[LifecycleOutcome, ...]:
        self._verify_policy_access(principal, "rag:query")
        self._require_aware(observed_at)
        if (
            self._retention_watermark is None
            or observed_at > self._retention_watermark
        ):
            self._retention_watermark = observed_at
        effective_observed_at = self._retention_watermark
        expired_ids = [
            document_id
            for document_id, expires_at in self._expires_at.items()
            if expires_at is not None and expires_at <= effective_observed_at
        ]
        outcomes: list[LifecycleOutcome] = []
        for document_id in sorted(expired_ids):
            document = self._documents.pop(document_id)
            self._content_owners.pop(document.content_sha256, None)
            self._expires_at.pop(document_id, None)
            self._discard_document_artifacts(document_id)
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

    @_serialized_state
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
        self.expire_documents(verified, observed_at=observed_at)
        result = execute_retrieval(
            request,
            verified,
            build_chunks(
                [self._documents[key] for key in sorted(self._documents)],
                chunk_size=chunk_size,
                overlap=overlap,
            ),
            self.cache,
            collection_version=self.collection_version,
        )
        chunks_by_document: dict[str, list[str]] = {}
        for chunk in result.retrieval.chunks:
            parsed_parents = self._fingerprints_for(
                chunk.document_id, ArtifactKind.PARSED
            )
            chunk_fingerprint = self._record_artifact(
                chunk.document_id,
                ArtifactKind.CHUNK,
                chunk.text,
                parent_fingerprints=parsed_parents,
                locator=chunk.chunk_id,
            )
            chunks_by_document.setdefault(chunk.document_id, []).append(
                chunk_fingerprint
            )
        for document_id, parent_fingerprints in chunks_by_document.items():
            self._record_artifact(
                document_id,
                ArtifactKind.CACHE,
                result.cache_key,
                parent_fingerprints=tuple(sorted(parent_fingerprints)),
                locator=result.cache_key,
            )
        return result

    def _resume_cascade(
        self,
        record: SourceRecord,
        state: _DeletionState,
        *,
        fail_after: ArtifactKind | None,
    ) -> DeletionResult:
        for index in range(state.next_cascade_index, len(CASCADE_ORDER)):
            kind = CASCADE_ORDER[index]
            removed = self._clear_artifact_kind(record.document_id, kind)
            state.invalidated_fingerprints[kind].update(removed)
            if kind == ArtifactKind.CACHE:
                self.cache.invalidate_collection(
                    self.policy.tenant_id, self.policy.collection_id
                )
                self._clear_all_cache_artifacts()
            state.next_cascade_index = index + 1
            if fail_after == kind:
                state.detail_code = f"cascade_pending_after_{kind.value}"
                return self._deletion_result(
                    record, state, state.detail_code
                )

        state.completed = True
        state.detail_code = (
            "tombstone_recorded_without_active_document"
            if state.missing_at_start
            else "tombstone_recorded_and_cascade_completed"
        )
        self._artifacts.pop(record.document_id, None)
        return self._deletion_result(record, state, state.detail_code)

    def _deletion_result(
        self,
        record: SourceRecord,
        state: _DeletionState,
        detail_code: str,
    ) -> DeletionResult:
        if state.completed:
            status = (
                LifecycleStatus.DELETE_NOT_FOUND
                if state.missing_at_start
                else LifecycleStatus.DELETED
            )
        else:
            status = LifecycleStatus.DELETE_PENDING
        outcome = LifecycleOutcome(
            document_id=record.document_id,
            source_version=record.source_version,
            status=status,
            collection_version=state.collection_version,
            detail_code=detail_code,
        )
        receipt = self._build_receipt(
            record, status, detail_code, state=state
        )
        return DeletionResult(outcome=outcome, receipt=receipt)

    def _version_conflict_result(self, record: SourceRecord) -> DeletionResult:
        outcome = self._outcome(
            record,
            LifecycleStatus.REJECTED_VERSION_CONFLICT,
            "delete_version_not_monotonic",
        )
        receipt = self._build_receipt(
            record,
            outcome.status,
            outcome.detail_code,
            state=None,
        )
        return DeletionResult(outcome=outcome, receipt=receipt)

    def _pending_delete_conflict_result(
        self, record: SourceRecord
    ) -> DeletionResult:
        outcome = self._outcome(
            record,
            LifecycleStatus.REJECTED_DELETE_PENDING,
            "prior_delete_cascade_pending",
        )
        receipt = self._build_receipt(
            record,
            outcome.status,
            outcome.detail_code,
            state=None,
        )
        return DeletionResult(outcome=outcome, receipt=receipt)

    def _build_receipt(
        self,
        record: SourceRecord,
        status: LifecycleStatus,
        detail_code: str,
        *,
        state: _DeletionState | None,
    ) -> DeletionReceipt:
        invalidations = tuple(
            ArtifactInvalidation(
                artifact_kind=kind,
                invalidated_count=(
                    len(state.invalidated_fingerprints[kind]) if state else 0
                ),
                artifact_fingerprints=(
                    tuple(sorted(state.invalidated_fingerprints[kind]))
                    if state
                    else ()
                ),
            )
            for kind in CASCADE_ORDER
        )
        return DeletionReceipt(
            operation_fingerprint=self._operation_fingerprint(
                record.document_id, record.source_version
            ),
            document_fingerprint=self._document_fingerprint(record.document_id),
            source_version=record.source_version,
            status=status,
            detail_code=detail_code,
            collection_version=(
                state.collection_version if state else self.collection_version
            ),
            invalidations=invalidations,
            reference_payload_copies_remaining=(
                self._reference_payload_copy_count(record.document_id)
            ),
            tombstone_retained=(
                state is not None
                and self._latest_versions.get(record.document_id)
                == record.source_version
            ),
            retryable=status in {
                LifecycleStatus.DELETE_PENDING,
                LifecycleStatus.REJECTED_DELETE_PENDING,
            },
        )

    def _record_ingested_artifacts(
        self, record: SourceRecord, document: Document
    ) -> None:
        raw_fingerprint = self._record_artifact(
            record.document_id,
            ArtifactKind.RAW,
            record.content,
            locator="source",
        )
        parsed_fingerprint = self._record_artifact(
            record.document_id,
            ArtifactKind.PARSED,
            document.text,
            parent_fingerprints=(raw_fingerprint,),
            locator="parsed",
        )
        for chunk in build_chunks([document]):
            self._record_artifact(
                record.document_id,
                ArtifactKind.CHUNK,
                chunk.text,
                parent_fingerprints=(parsed_fingerprint,),
                locator=chunk.chunk_id,
            )

    def _record_artifact(
        self,
        document_id: str,
        artifact_kind: ArtifactKind,
        payload: bytes | str,
        *,
        parent_fingerprints: tuple[str, ...] = (),
        locator: str = "derived",
    ) -> str:
        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        if not isinstance(encoded, bytes):
            raise TypeError("artifact payload must be bytes or str")
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError("document_not_active")
        canonical_parents = tuple(sorted(set(parent_fingerprints)))
        fingerprint_material = json.dumps(
            {
                "artifact_kind": artifact_kind.value,
                "collection_id": self.policy.collection_id,
                "document_id": document_id,
                "locator": locator,
                "parent_fingerprints": canonical_parents,
                "payload_sha256": sha256(encoded).hexdigest(),
                "source_version": document.source_version,
                "tenant_id": self.policy.tenant_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        fingerprint = sha256(fingerprint_material.encode("utf-8")).hexdigest()
        stores = self._artifacts.setdefault(document_id, {})
        stores.setdefault(artifact_kind, {})[fingerprint] = _ArtifactCopy(
            payload=encoded,
            parent_fingerprints=canonical_parents,
        )
        return fingerprint

    def _active_parent_kinds(
        self, document_id: str, parent_fingerprints: tuple[str, ...]
    ) -> set[ArtifactKind]:
        if len(set(parent_fingerprints)) != len(parent_fingerprints):
            raise ValueError("duplicate_lineage_parent")
        active = {
            fingerprint: kind
            for kind, copies in self._artifacts.get(document_id, {}).items()
            for fingerprint in copies
        }
        missing = set(parent_fingerprints).difference(active)
        if missing:
            raise ValueError("lineage_parent_not_active")
        return {active[fingerprint] for fingerprint in parent_fingerprints}

    def _artifact_kind(
        self, document_id: str, artifact_fingerprint: str
    ) -> ArtifactKind:
        for kind, copies in self._artifacts.get(document_id, {}).items():
            if artifact_fingerprint in copies:
                return kind
        raise ValueError("lineage_parent_not_active")

    def _lineage_has_ancestor(
        self,
        document_id: str,
        *,
        descendant_fingerprint: str,
        ancestor_fingerprint: str,
    ) -> bool:
        copies = {
            fingerprint: copy
            for kind_copies in self._artifacts.get(document_id, {}).values()
            for fingerprint, copy in kind_copies.items()
        }
        pending = [descendant_fingerprint]
        visited: set[str] = set()
        while pending:
            fingerprint = pending.pop()
            if fingerprint in visited:
                continue
            visited.add(fingerprint)
            copy = copies.get(fingerprint)
            if copy is None:
                continue
            if ancestor_fingerprint in copy.parent_fingerprints:
                return True
            pending.extend(copy.parent_fingerprints)
        return False

    def _fingerprints_for(
        self, document_id: str, kind: ArtifactKind
    ) -> tuple[str, ...]:
        return tuple(
            sorted(self._artifacts.get(document_id, {}).get(kind, {}))
        )

    def _clear_artifact_kind(
        self, document_id: str, kind: ArtifactKind
    ) -> tuple[str, ...]:
        stores = self._artifacts.get(document_id)
        if stores is None:
            return ()
        removed = tuple(sorted(stores.pop(kind, {})))
        if not stores:
            self._artifacts.pop(document_id, None)
        return removed

    def _discard_document_artifacts(self, document_id: str) -> None:
        self._artifacts.pop(document_id, None)

    def _clear_all_cache_artifacts(self) -> None:
        for document_id in tuple(self._artifacts):
            stores = self._artifacts.get(document_id)
            if stores is None:
                continue
            invalidated = set(stores.get(ArtifactKind.CACHE, {}))
            if not invalidated:
                continue

            # A prompt may bind to a cached retrieval artifact. Once that cache
            # is invalid, every transitive descendant is invalid as well.
            changed = True
            while changed:
                changed = False
                for copies in stores.values():
                    for fingerprint, copy in copies.items():
                        if fingerprint in invalidated:
                            continue
                        if invalidated.intersection(copy.parent_fingerprints):
                            invalidated.add(fingerprint)
                            changed = True

            for kind in tuple(stores):
                copies = stores[kind]
                for fingerprint in invalidated:
                    copies.pop(fingerprint, None)
                if not copies:
                    stores.pop(kind)
            if not stores:
                self._artifacts.pop(document_id, None)

    def _reference_payload_copy_count(self, document_id: str) -> int:
        return sum(
            len(copies)
            for copies in self._artifacts.get(document_id, {}).values()
        )

    def _ingest_state_conflict(
        self, record: SourceRecord
    ) -> LifecycleOutcome | None:
        deletion_state = self._deletions.get(record.document_id)
        if deletion_state is not None and not deletion_state.completed:
            return self._outcome(
                record,
                LifecycleStatus.REJECTED_DELETE_PENDING,
                "delete_cascade_pending",
            )
        latest_version = self._latest_versions.get(record.document_id)
        if latest_version is not None and record.source_version <= latest_version:
            return self._outcome(
                record,
                LifecycleStatus.REJECTED_VERSION_CONFLICT,
                "source_version_not_monotonic",
            )
        return None

    def _record_is_expired(
        self, record: SourceRecord, observed_at: datetime
    ) -> bool:
        if record.expires_at is None:
            return False
        effective_observed_at = observed_at
        if (
            self._retention_watermark is not None
            and self._retention_watermark > effective_observed_at
        ):
            effective_observed_at = self._retention_watermark
        return record.expires_at <= effective_observed_at

    def _verify_policy_access(
        self, principal: Principal | None, scope: str
    ) -> Principal:
        verified = self._verify_principal(principal, scope)
        if (
            self.policy.permission_group
            not in verified.effective_permission_groups
        ):
            raise InsufficientScope(
                "lifecycle_policy_permission_group_mismatch"
            )
        return verified

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
        self._clear_all_cache_artifacts()

    def _outcome(
        self,
        record: SourceRecord,
        status: LifecycleStatus,
        detail_code: str,
        parse_report: ParseQualityReport | None = None,
    ) -> LifecycleOutcome:
        return LifecycleOutcome(
            document_id=record.document_id,
            source_version=record.source_version,
            status=status,
            collection_version=self.collection_version,
            detail_code=detail_code,
            parse_report=parse_report,
        )

    def _document_fingerprint(self, document_id: str) -> str:
        payload = json.dumps(
            {
                "tenant_id": self.policy.tenant_id,
                "collection_id": self.policy.collection_id,
                "document_id": document_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def _operation_fingerprint(
        self, document_id: str, source_version: int
    ) -> str:
        return sha256(
            (
                self._document_fingerprint(document_id)
                + f":delete:{source_version}"
            ).encode("ascii")
        ).hexdigest()
