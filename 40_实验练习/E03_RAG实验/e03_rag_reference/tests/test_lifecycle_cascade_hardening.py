from datetime import datetime, timezone

import pytest

from rag_reference.ingestion import TrustedCollectionPolicy
from rag_reference.lifecycle import (
    ArtifactKind,
    LifecycleIndex,
    LifecycleStatus,
    SourceRecord,
)
from rag_reference.security import Principal
from rag_reference.service import RagQueryRequest


NOW = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)


def principal() -> Principal:
    return Principal(
        tenant_id="tenant-demo",
        user_id="cascade-hardening",
        scopes=frozenset({"rag:ingest", "rag:delete", "rag:query"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )


def policy() -> TrustedCollectionPolicy:
    return TrustedCollectionPolicy(
        tenant_id="tenant-demo",
        collection_id="demo",
        permission_group="public",
        source_id="cascade-hardening-fixture",
        source_version="v1",
    )


def ingest_document(index: LifecycleIndex, *, version: int = 1) -> SourceRecord:
    record = SourceRecord(
        document_id="doc-cascade-hardening",
        content=(
            b"CHUNK-A lineage evidence "
            + (b"a" * 90)
            + b" CHUNK-B separate evidence "
            + (b"b" * 90)
        ),
        media_type="text/plain",
        source_version=version,
    )
    outcome = index.ingest(record, principal(), observed_at=NOW)
    assert outcome.status == LifecycleStatus.ACCEPTED
    return record


def inventory(index: LifecycleIndex) -> dict[ArtifactKind, tuple[str, ...]]:
    return {
        entry.artifact_kind: entry.artifact_fingerprints
        for entry in index.artifact_inventory(
            "doc-cascade-hardening", principal()
        )
    }


def test_new_ingest_cannot_overtake_pending_delete_cascade():
    index = LifecycleIndex(policy())
    ingest_document(index)
    pending = index.delete_with_receipt(
        "doc-cascade-hardening",
        2,
        principal(),
        fail_after=ArtifactKind.RAW,
    )
    assert pending.outcome.status == LifecycleStatus.DELETE_PENDING

    attempted = index.ingest(
        SourceRecord(
            "doc-cascade-hardening",
            b"fresh content must wait for cascade completion",
            "text/plain",
            3,
        ),
        principal(),
        observed_at=NOW,
    )
    assert attempted.status == LifecycleStatus.REJECTED_DELETE_PENDING
    assert attempted.detail_code == "delete_cascade_pending"
    assert index.active_documents(principal()) == ()

    completed = index.delete_with_receipt(
        "doc-cascade-hardening", 2, principal()
    )
    assert completed.outcome.status == LifecycleStatus.DELETED
    accepted = index.ingest(
        SourceRecord(
            "doc-cascade-hardening",
            b"fresh content after completed cascade",
            "text/plain",
            3,
        ),
        principal(),
        observed_at=NOW,
    )
    assert accepted.status == LifecycleStatus.ACCEPTED
    assert inventory(index)[ArtifactKind.RAW]


def test_newer_delete_cannot_replace_pending_delete_state():
    index = LifecycleIndex(policy())
    ingest_document(index)
    pending = index.delete_with_receipt(
        "doc-cascade-hardening",
        2,
        principal(),
        fail_after=ArtifactKind.PARSED,
    )
    operation_fingerprint = pending.receipt.operation_fingerprint

    rejected = index.delete_with_receipt(
        "doc-cascade-hardening", 3, principal()
    )
    assert rejected.outcome.status == LifecycleStatus.REJECTED_DELETE_PENDING
    assert rejected.outcome.detail_code == "prior_delete_cascade_pending"
    assert rejected.receipt.retryable

    completed = index.delete_with_receipt(
        "doc-cascade-hardening", 2, principal()
    )
    assert completed.receipt.operation_fingerprint == operation_fingerprint
    assert completed.outcome.status == LifecycleStatus.DELETED


def test_citation_chunk_must_be_in_output_lineage():
    index = LifecycleIndex(policy())
    ingest_document(index)
    artifacts = inventory(index)
    chunks = artifacts[ArtifactKind.CHUNK]
    assert len(chunks) >= 2

    prompt = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.PROMPT,
        "prompt based on the first chunk",
        principal(),
        parent_fingerprints=(chunks[0],),
    )
    output = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.OUTPUT,
        "output based on that prompt",
        principal(),
        parent_fingerprints=(prompt,),
    )
    second_prompt = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.PROMPT,
        "prompt based on the first chunk",
        principal(),
        parent_fingerprints=(chunks[1],),
    )
    assert second_prompt != prompt

    with pytest.raises(ValueError, match="lineage_parent_kind_mismatch"):
        index.register_derived_artifact(
            "doc-cascade-hardening",
            ArtifactKind.OUTPUT,
            "output with a smuggled raw parent",
            principal(),
            parent_fingerprints=(prompt, artifacts[ArtifactKind.RAW][0]),
        )
    with pytest.raises(ValueError, match="lineage_parent_cardinality_mismatch"):
        index.register_derived_artifact(
            "doc-cascade-hardening",
            ArtifactKind.CITATION,
            "mixed citation",
            principal(),
            parent_fingerprints=(output, chunks[0], chunks[1]),
        )

    try:
        index.register_derived_artifact(
            "doc-cascade-hardening",
            ArtifactKind.CITATION,
            "wrong citation",
            principal(),
            parent_fingerprints=(output, chunks[1]),
        )
    except ValueError as error:
        assert str(error) == "citation_chunk_not_in_output_lineage"
    else:
        raise AssertionError("unrelated citation chunk must be rejected")

    citation = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.CITATION,
        "correct citation",
        principal(),
        parent_fingerprints=(output, chunks[0]),
    )
    assert citation


def test_lineage_parent_order_is_canonical_and_duplicates_are_rejected():
    index = LifecycleIndex(policy())
    ingest_document(index)
    chunks = inventory(index)[ArtifactKind.CHUNK]
    assert len(chunks) >= 2

    forward = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.PROMPT,
        "canonical parent order",
        principal(),
        parent_fingerprints=(chunks[0], chunks[1]),
    )
    reverse = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.PROMPT,
        "canonical parent order",
        principal(),
        parent_fingerprints=(chunks[1], chunks[0]),
    )
    assert reverse == forward

    with pytest.raises(ValueError, match="duplicate_lineage_parent"):
        index.register_derived_artifact(
            "doc-cascade-hardening",
            ArtifactKind.PROMPT,
            "duplicate parent",
            principal(),
            parent_fingerprints=(chunks[0], chunks[0]),
        )


def test_collection_change_invalidates_cache_lineage_descendants():
    index = LifecycleIndex(policy())
    ingest_document(index)
    result = index.query(
        RagQueryRequest("CHUNK-A lineage evidence", "demo", 1),
        principal(),
        observed_at=NOW,
    )
    assert result.retrieval.chunks

    entries = {
        entry.artifact_kind: entry
        for entry in index.artifact_inventory(
            "doc-cascade-hardening", principal()
        )
    }
    cache = entries[ArtifactKind.CACHE].artifact_fingerprints[0]
    cited_chunk = entries[ArtifactKind.CACHE].parent_fingerprints[0]
    prompt = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.PROMPT,
        "prompt derived from cached retrieval",
        principal(),
        parent_fingerprints=(cache,),
    )
    output = index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.OUTPUT,
        "output derived from cached retrieval",
        principal(),
        parent_fingerprints=(prompt,),
    )
    index.register_derived_artifact(
        "doc-cascade-hardening",
        ArtifactKind.CITATION,
        "citation derived from cached retrieval",
        principal(),
        parent_fingerprints=(output, cited_chunk),
    )

    unrelated = index.ingest(
        SourceRecord(
            "doc-unrelated-generation",
            b"unrelated document advances the collection generation",
            "text/plain",
            1,
        ),
        principal(),
        observed_at=NOW,
    )
    assert unrelated.status == LifecycleStatus.ACCEPTED

    remaining = inventory(index)
    assert remaining[ArtifactKind.CHUNK]
    for kind in (
        ArtifactKind.CACHE,
        ArtifactKind.PROMPT,
        ArtifactKind.OUTPUT,
        ArtifactKind.CITATION,
    ):
        assert remaining[kind] == ()
