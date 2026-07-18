import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rag_reference.ingestion import TrustedCollectionPolicy
from rag_reference.lifecycle import LifecycleIndex, LifecycleStatus, SourceRecord
from rag_reference.security import AuthenticationRequired, InsufficientScope, Principal
from rag_reference.service import RagQueryRequest, RetrievalCache


FIXTURES = Path(__file__).parent / "fixtures"


def principal() -> Principal:
    return Principal(
        tenant_id="tenant-demo",
        user_id="lifecycle-test",
        scopes=frozenset({"rag:ingest", "rag:delete", "rag:query"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )


def policy() -> TrustedCollectionPolicy:
    return TrustedCollectionPolicy(
        tenant_id="tenant-demo",
        collection_id="demo",
        permission_group="public",
        source_id="lifecycle-fixture",
        source_version="server-policy-v1",
    )


def _record(case: dict) -> SourceRecord:
    if "content_base64" in case:
        content = base64.b64decode(case["content_base64"])
    else:
        content = case["content_utf8"].encode("utf-8")
    expires_at = (
        datetime.fromisoformat(case["expires_at"])
        if "expires_at" in case
        else None
    )
    return SourceRecord(
        document_id=case["document_id"],
        content=content,
        media_type=case["media_type"],
        source_version=case["source_version"],
        expires_at=expires_at,
    )


def test_ingestion_failure_matrix_has_a_deterministic_status_for_each_case():
    fixture = json.loads(
        (FIXTURES / "ingestion_failure_matrix.json").read_text(encoding="utf-8")
    )
    observed_at = datetime.fromisoformat(fixture["observed_at"])
    index = LifecycleIndex(policy())
    actual: dict[str, str] = {}

    for case in fixture["cases"]:
        if case["operation"] == "delete":
            outcome = index.delete(
                case["document_id"], case["source_version"], principal()
            )
        else:
            outcome = index.ingest(
                _record(case), principal(), observed_at=observed_at
            )
        actual[case["case_id"]] = outcome.status.value

    assert actual == {
        case["case_id"]: case["expected_status"] for case in fixture["cases"]
    }
    assert index.documents == ()


def test_delete_invalidates_cached_result_and_prevents_stale_resurrection():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    cache = RetrievalCache()
    index = LifecycleIndex(policy(), cache)
    record = SourceRecord(
        document_id="doc-delete-me",
        content=b"MAGIC-LIFECYCLE-912 deletion evidence",
        media_type="text/plain",
        source_version=1,
    )
    assert index.ingest(record, principal(), observed_at=now).status == LifecycleStatus.ACCEPTED
    request = RagQueryRequest("MAGIC-LIFECYCLE-912", "demo", 1)

    first = index.query(request, principal(), observed_at=now)
    repeat = index.query(request, principal(), observed_at=now)
    assert first.retrieval.chunks[0].document_id == "doc-delete-me"
    assert not first.cache_hit
    assert repeat.cache_hit
    assert cache.entry_count == 1

    deleted = index.delete("doc-delete-me", 2, principal())
    assert deleted.status == LifecycleStatus.DELETED
    assert cache.entry_count == 0

    after_delete = index.query(request, principal(), observed_at=now)
    assert not after_delete.cache_hit
    assert after_delete.retrieval.chunks == ()
    assert all(
        chunk.document_id != "doc-delete-me"
        for chunk in after_delete.retrieval.chunks
    )

    stale = index.ingest(record, principal(), observed_at=now)
    assert stale.status == LifecycleStatus.REJECTED_VERSION_CONFLICT
    assert index.documents == ()


def test_missing_document_delete_records_tombstone_before_stale_ingestion_arrives():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    index = LifecycleIndex(policy())

    deleted = index.delete("doc-out-of-order", 5, principal())

    assert deleted.status == LifecycleStatus.DELETE_NOT_FOUND
    assert deleted.detail_code == "tombstone_recorded_without_active_document"
    assert deleted.collection_version == "lifecycle-000001"
    stale = index.ingest(
        SourceRecord(
            document_id="doc-out-of-order",
            content=b"stale version four",
            media_type="text/plain",
            source_version=4,
        ),
        principal(),
        observed_at=now,
    )
    assert stale.status == LifecycleStatus.REJECTED_VERSION_CONFLICT
    assert index.documents == ()

    fresh = index.ingest(
        SourceRecord(
            document_id="doc-out-of-order",
            content=b"fresh version six",
            media_type="text/plain",
            source_version=6,
        ),
        principal(),
        observed_at=now,
    )
    assert fresh.status == LifecycleStatus.ACCEPTED


def test_query_authorization_fails_before_retention_can_mutate_state():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    cache = RetrievalCache()
    index = LifecycleIndex(policy(), cache)
    index.ingest(
        SourceRecord(
            document_id="doc-auth-before-expiry",
            content=b"AUTH-BEFORE-EXPIRY-731 evidence",
            media_type="text/plain",
            source_version=1,
            expires_at=now + timedelta(minutes=5),
        ),
        principal(),
        observed_at=now,
    )
    request = RagQueryRequest("AUTH-BEFORE-EXPIRY-731", "demo", 1)
    index.query(request, principal(), observed_at=now)
    baseline_version = index.collection_version
    assert cache.entry_count == 1

    missing_scope = Principal(
        tenant_id="tenant-demo",
        user_id="missing-query-scope",
        scopes=frozenset({"rag:ingest"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )
    wrong_tenant = Principal(
        tenant_id="tenant-other",
        user_id="wrong-tenant",
        scopes=frozenset({"rag:query"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )
    unauthorized_callers = (
        (None, AuthenticationRequired),
        (missing_scope, InsufficientScope),
        (wrong_tenant, InsufficientScope),
    )
    after_expiry = now + timedelta(minutes=6)
    for caller, expected_error in unauthorized_callers:
        with pytest.raises(expected_error):
            index.query(request, caller, observed_at=after_expiry)
        assert tuple(document.document_id for document in index.documents) == (
            "doc-auth-before-expiry",
        )
        assert index.collection_version == baseline_version
        assert cache.entry_count == 1

    authorized = index.query(request, principal(), observed_at=after_expiry)
    assert authorized.retrieval.chunks == ()
    assert index.collection_version != baseline_version
    assert cache.entry_count == 1


def test_retention_expiry_removes_document_and_invalidates_cache():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    cache = RetrievalCache()
    index = LifecycleIndex(policy(), cache)
    index.ingest(
        SourceRecord(
            document_id="doc-short-lived",
            content=b"SHORT-LIVED-441 evidence",
            media_type="text/plain",
            source_version=1,
            expires_at=now + timedelta(minutes=5),
        ),
        principal(),
        observed_at=now,
    )
    request = RagQueryRequest("SHORT-LIVED-441", "demo", 1)
    assert index.query(request, principal(), observed_at=now).retrieval.chunks
    assert cache.entry_count == 1

    expired = index.expire_documents(observed_at=now + timedelta(minutes=6))

    assert [outcome.status for outcome in expired] == [LifecycleStatus.EXPIRED]
    assert cache.entry_count == 0
    result = index.query(
        request, principal(), observed_at=now + timedelta(minutes=6)
    )
    assert not result.cache_hit
    assert result.retrieval.chunks == ()
