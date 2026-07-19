import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Event

import pytest

from rag_reference.ingestion import TrustedCollectionPolicy
from rag_reference.lifecycle import (
    ArtifactKind,
    LifecycleIndex,
    LifecycleStatus,
    SourceRecord,
)
from rag_reference.parsing import AdapterExtraction
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
    assert index.active_documents(principal()) == ()


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
    assert index.active_documents(principal()) == ()


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
    assert index.active_documents(principal()) == ()

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
        assert tuple(
            document.document_id
            for document in index.active_documents(principal())
        ) == (
            "doc-auth-before-expiry",
        )
        assert index.collection_version == baseline_version
        assert cache.entry_count == 1

    authorized = index.query(request, principal(), observed_at=after_expiry)
    assert authorized.retrieval.chunks == ()
    assert index.collection_version != baseline_version
    assert cache.entry_count == 1


def test_artifact_inventory_authorization_does_not_leak_document_existence():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    index = LifecycleIndex(policy())
    index.ingest(
        SourceRecord(
            document_id="doc-inventory-private",
            content=b"private inventory evidence",
            media_type="text/plain",
            source_version=1,
        ),
        principal(),
        observed_at=now,
    )
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
    missing_permission_group = Principal(
        tenant_id="tenant-demo",
        user_id="missing-permission-group",
        scopes=frozenset({"rag:query"}),
        effective_permission_groups=frozenset({"restricted"}),
        acl_version="acl-v1",
    )

    unauthorized_callers = (
        (None, AuthenticationRequired, "authentication_required"),
        (missing_scope, InsufficientScope, "missing_scope:rag:query"),
        (
            wrong_tenant,
            InsufficientScope,
            "lifecycle_policy_tenant_mismatch",
        ),
        (
            missing_permission_group,
            InsufficientScope,
            "lifecycle_policy_permission_group_mismatch",
        ),
    )
    for caller, expected_error, expected_message in unauthorized_callers:
        with pytest.raises(expected_error) as active_error:
            index.active_documents(caller)
        assert str(active_error.value) == expected_message
        observed_errors = []
        for document_id in ("doc-inventory-private", "doc-does-not-exist"):
            with pytest.raises(expected_error) as error:
                index.artifact_inventory(document_id, caller)
            observed_errors.append(str(error.value))
        assert observed_errors == [expected_message, expected_message]

    authorized = index.artifact_inventory(
        "doc-inventory-private", principal()
    )
    assert sum(entry.active_count for entry in authorized) > 0


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

    expired = index.expire_documents(
        principal(), observed_at=now + timedelta(minutes=6)
    )

    assert [outcome.status for outcome in expired] == [LifecycleStatus.EXPIRED]
    assert cache.entry_count == 0
    result = index.query(
        request, principal(), observed_at=now + timedelta(minutes=6)
    )
    assert not result.cache_hit
    assert result.retrieval.chunks == ()


def test_direct_retention_expiry_requires_policy_authorization_before_mutation():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    cache = RetrievalCache()
    index = LifecycleIndex(policy(), cache)
    index.ingest(
        SourceRecord(
            "doc-direct-expiry-auth",
            b"DIRECT-EXPIRY-AUTH-919 evidence",
            "text/plain",
            1,
            expires_at=now + timedelta(minutes=1),
        ),
        principal(),
        observed_at=now,
    )
    request = RagQueryRequest("DIRECT-EXPIRY-AUTH-919", "demo", 1)
    index.query(request, principal(), observed_at=now)
    baseline_version = index.collection_version
    assert cache.entry_count == 1

    unauthorized_callers = (
        (
            None,
            AuthenticationRequired,
            "authentication_required",
        ),
        (
            Principal(
                tenant_id="tenant-demo",
                user_id="missing-query-scope",
                scopes=frozenset({"rag:ingest"}),
                effective_permission_groups=frozenset({"public"}),
                acl_version="acl-v1",
            ),
            InsufficientScope,
            "missing_scope:rag:query",
        ),
        (
            Principal(
                tenant_id="tenant-other",
                user_id="wrong-tenant",
                scopes=frozenset({"rag:query"}),
                effective_permission_groups=frozenset({"public"}),
                acl_version="acl-v1",
            ),
            InsufficientScope,
            "lifecycle_policy_tenant_mismatch",
        ),
        (
            Principal(
                tenant_id="tenant-demo",
                user_id="wrong-group",
                scopes=frozenset({"rag:query"}),
                effective_permission_groups=frozenset({"restricted"}),
                acl_version="acl-v1",
            ),
            InsufficientScope,
            "lifecycle_policy_permission_group_mismatch",
        ),
    )
    observed_at = now + timedelta(minutes=2)
    for caller, expected_error, expected_message in unauthorized_callers:
        with pytest.raises(expected_error) as error:
            index.expire_documents(caller, observed_at=observed_at)
        assert str(error.value) == expected_message
        assert index.collection_version == baseline_version
        assert cache.entry_count == 1
        assert len(index.active_documents(principal())) == 1

    expired = index.expire_documents(principal(), observed_at=observed_at)
    assert [outcome.status for outcome in expired] == [LifecycleStatus.EXPIRED]
    assert index.active_documents(principal()) == ()
    assert cache.entry_count == 0


def test_concurrent_delete_tombstone_wins_over_slow_ingestion_commit():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    parse_started = Event()
    release_parse = Event()

    def blocking_adapter(content: bytes, limits: object) -> AdapterExtraction:
        del content, limits
        parse_started.set()
        if not release_parse.wait(timeout=5):
            raise TimeoutError("test adapter release timed out")
        return AdapterExtraction("CONCURRENT-TOMBSTONE-771 stale content")

    index = LifecycleIndex(
        policy(), parser_adapters={"image/png": blocking_adapter}
    )
    record = SourceRecord(
        "doc-concurrent-tombstone",
        b"\x89PNG\r\n\x1a\nblocking-fixture",
        "image/png",
        2,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        ingest_future = executor.submit(
            index.ingest, record, principal(), observed_at=now
        )
        try:
            assert parse_started.wait(timeout=5)
            deleted = index.delete("doc-concurrent-tombstone", 3, principal())
        finally:
            release_parse.set()
        ingested = ingest_future.result(timeout=5)

    assert deleted.status == LifecycleStatus.DELETE_NOT_FOUND
    assert ingested.status == LifecycleStatus.REJECTED_VERSION_CONFLICT
    assert index.active_documents(principal()) == ()
    stale_retry = index.ingest(record, principal(), observed_at=now)
    assert stale_retry.status == LifecycleStatus.REJECTED_VERSION_CONFLICT


def test_retention_watermark_rejects_slow_ingestion_that_expires_during_parse():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    expires_at = now + timedelta(minutes=1)
    parse_started = Event()
    release_parse = Event()

    def blocking_adapter(content: bytes, limits: object) -> AdapterExtraction:
        del content, limits
        parse_started.set()
        if not release_parse.wait(timeout=5):
            raise TimeoutError("test adapter release timed out")
        return AdapterExtraction("new version that expired while parsing")

    index = LifecycleIndex(
        policy(), parser_adapters={"image/png": blocking_adapter}
    )
    index.ingest(
        SourceRecord(
            "doc-retention-race",
            b"initial version",
            "text/plain",
            1,
            expires_at=expires_at,
        ),
        principal(),
        observed_at=now,
    )
    record = SourceRecord(
        "doc-retention-race",
        b"\x89PNG\r\n\x1a\nslow-version",
        "image/png",
        2,
        expires_at=expires_at,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        ingest_future = executor.submit(
            index.ingest, record, principal(), observed_at=now
        )
        try:
            assert parse_started.wait(timeout=5)
            expired = index.expire_documents(
                principal(), observed_at=now + timedelta(minutes=2)
            )
        finally:
            release_parse.set()
        ingested = ingest_future.result(timeout=5)

    assert [outcome.status for outcome in expired] == [LifecycleStatus.EXPIRED]
    assert ingested.status == LifecycleStatus.REJECTED_EXPIRED
    assert ingested.detail_code == "expired_before_commit"
    assert index.active_documents(principal()) == ()


def test_same_document_can_advance_version_without_changing_parsed_content():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
    index = LifecycleIndex(policy())
    first = index.ingest(
        SourceRecord("doc-same-content", b"stable content", "text/plain", 1),
        principal(),
        observed_at=now,
    )
    updated = index.ingest(
        SourceRecord(
            "doc-same-content",
            b"stable content",
            "text/plain",
            2,
            expires_at=now + timedelta(days=1),
        ),
        principal(),
        observed_at=now,
    )
    duplicate = index.ingest(
        SourceRecord("doc-other", b"stable content", "text/plain", 1),
        principal(),
        observed_at=now,
    )

    assert first.status == LifecycleStatus.ACCEPTED
    assert updated.status == LifecycleStatus.UPDATED
    assert duplicate.status == LifecycleStatus.REJECTED_DUPLICATE
    active = index.active_documents(principal())
    assert [(document.document_id, document.source_version) for document in active] == [
        ("doc-same-content", "2")
    ]


def test_mutating_lifecycle_apis_reject_unauthorized_callers_without_side_effects():
    now = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)

    def build_index() -> LifecycleIndex:
        result = LifecycleIndex(policy())
        result.ingest(
            SourceRecord(
                "doc-mutation-auth",
                b"mutation authorization baseline",
                "text/plain",
                1,
            ),
            principal(),
            observed_at=now,
        )
        return result

    for operation, required_scope in (
        ("ingest", "rag:ingest"),
        ("register", "rag:ingest"),
        ("delete", "rag:delete"),
    ):
        callers = (
            (None, AuthenticationRequired, "authentication_required"),
            (
                Principal(
                    tenant_id="tenant-demo",
                    user_id="missing-scope",
                    scopes=frozenset({"rag:query"}),
                    effective_permission_groups=frozenset({"public"}),
                    acl_version="acl-v1",
                ),
                InsufficientScope,
                f"missing_scope:{required_scope}",
            ),
            (
                Principal(
                    tenant_id="tenant-other",
                    user_id="wrong-tenant",
                    scopes=frozenset({required_scope}),
                    effective_permission_groups=frozenset({"public"}),
                    acl_version="acl-v1",
                ),
                InsufficientScope,
                "lifecycle_policy_tenant_mismatch",
            ),
        )
        for caller, expected_error, expected_message in callers:
            index = build_index()
            baseline_version = index.collection_version
            baseline_documents = index.active_documents(principal())
            baseline_inventory = index.artifact_inventory(
                "doc-mutation-auth", principal()
            )
            parsed = next(
                entry.artifact_fingerprints[0]
                for entry in baseline_inventory
                if entry.artifact_kind.value == "parsed"
            )

            with pytest.raises(expected_error) as error:
                if operation == "ingest":
                    index.ingest(
                        SourceRecord(
                            "doc-mutation-auth",
                            b"unauthorized update",
                            "text/plain",
                            2,
                        ),
                        caller,
                        observed_at=now,
                    )
                elif operation == "register":
                    index.register_derived_artifact(
                        "doc-mutation-auth",
                        ArtifactKind.VECTOR,
                        "unauthorized vector",
                        caller,
                        parent_fingerprints=(parsed,),
                    )
                else:
                    index.delete("doc-mutation-auth", 2, caller)

            assert str(error.value) == expected_message
            assert index.collection_version == baseline_version
            assert index.active_documents(principal()) == baseline_documents
            assert (
                index.artifact_inventory("doc-mutation-auth", principal())
                == baseline_inventory
            )
