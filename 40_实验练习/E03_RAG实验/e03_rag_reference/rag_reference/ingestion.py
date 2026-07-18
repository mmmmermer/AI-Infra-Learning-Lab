from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .corpus import Document
from .security import InsufficientScope, Principal, require_scope
from .service import RequestValidationError


INGEST_REQUEST_FIELDS = frozenset({"document_id", "text"})
INGEST_FORBIDDEN_FIELDS = frozenset(
    {
        "tenant_id",
        "user_id",
        "owner_id",
        "collection_id",
        "permission_group",
        "permission_groups",
        "allowed_permission_groups",
        "source_id",
        "source_version",
    }
)


@dataclass(frozen=True)
class DocumentIngestRequest:
    document_id: str
    text: str


@dataclass(frozen=True)
class TrustedCollectionPolicy:
    tenant_id: str
    collection_id: str
    permission_group: str
    source_id: str
    source_version: str


def parse_document_ingest_request(
    payload: Mapping[str, object],
) -> DocumentIngestRequest:
    supplied = set(payload)
    forged = supplied.intersection(INGEST_FORBIDDEN_FIELDS)
    if forged:
        raise RequestValidationError("forged_ingestion_metadata", forged)
    unknown = supplied.difference(INGEST_REQUEST_FIELDS)
    if unknown:
        raise RequestValidationError("unknown_fields", unknown)
    missing = INGEST_REQUEST_FIELDS.difference(supplied)
    if missing:
        raise RequestValidationError("missing_fields", missing)

    document_id = payload["document_id"]
    content = payload["text"]
    malformed: set[str] = set()
    if not isinstance(document_id, str) or not document_id.strip():
        malformed.add("document_id")
    if not isinstance(content, str) or not content.strip():
        malformed.add("text")
    if malformed:
        raise RequestValidationError("malformed_fields", malformed)
    return DocumentIngestRequest(document_id.strip(), content.strip())


def ingest_document(
    request: DocumentIngestRequest,
    principal: Principal | None,
    policy: TrustedCollectionPolicy,
) -> Document:
    verified = require_scope(principal, "rag:ingest")
    if verified.tenant_id != policy.tenant_id:
        raise InsufficientScope("ingestion_policy_tenant_mismatch")
    return Document(
        document_id=request.document_id,
        permission_group=policy.permission_group,
        text=request.text,
        tenant_id=policy.tenant_id,
        collection_id=policy.collection_id,
        source_id=policy.source_id,
        source_version=policy.source_version,
    )
