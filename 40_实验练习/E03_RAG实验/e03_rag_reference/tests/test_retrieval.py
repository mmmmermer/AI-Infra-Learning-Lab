import pytest

from rag_reference.corpus import DOCUMENTS, GOLD_QUERIES, Document
from rag_reference.retrieval import build_chunks, evaluate_queries, retrieve
from rag_reference.security import AuthenticationRequired, InsufficientScope, Principal
from rag_reference.service import (
    RagQueryRequest,
    RequestValidationError,
    RetrievalCache,
    execute_retrieval,
    parse_rag_query_request,
)


def principal(
    *groups: str,
    tenant_id: str = "tenant-demo",
    acl_version: str = "acl-v1",
    scopes: frozenset[str] = frozenset({"rag:query"}),
) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        user_id="user-test",
        scopes=scopes,
        effective_permission_groups=frozenset(groups),
        acl_version=acl_version,
    )


def test_gold_queries_retrieve_expected_documents():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)

    rows = evaluate_queries(GOLD_QUERIES, chunks, top_k=3)

    assert all(row.recall_at_k == 1.0 for row in rows)
    assert all(row.reciprocal_rank > 0 for row in rows)
    assert all(row.retrieval_ms >= 0 for row in rows)


def test_permission_filter_is_applied_before_bm25_scoring_and_candidates():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)
    private_chunk_ids = {
        chunk.chunk_id
        for chunk in chunks
        if chunk.permission_group == "compliance_private"
    }

    result = retrieve(
        "客户 ZETA 为什么需要额外人工复核？",
        chunks,
        principal("public"),
        top_k=5,
    )

    assert private_chunk_ids.isdisjoint(result.scored_chunk_ids)
    assert result.authorized_search_space_size == len(result.scored_chunk_ids)
    assert all(chunk.permission_group == "public" for chunk in result.chunks)
    assert all(chunk.document_id != "doc_compliance_private_001" for chunk in result.chunks)


def test_authorized_user_can_retrieve_private_document():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)

    result = retrieve(
        "客户 ZETA 为什么需要额外人工复核？",
        chunks,
        principal("public", "compliance_private"),
        top_k=3,
    )

    assert result.chunks[0].document_id == "doc_compliance_private_001"


def test_tenant_filter_is_applied_before_scoring():
    documents = [
        *DOCUMENTS,
        Document(
            "doc_other_tenant_secret",
            "public",
            "唯一跨租户秘密词 OMEGA-912 不得被其他租户检索。",
            tenant_id="tenant-other",
        ),
    ]
    chunks = build_chunks(documents, chunk_size=80, overlap=10)
    other_tenant_chunk_ids = {
        chunk.chunk_id for chunk in chunks if chunk.tenant_id == "tenant-other"
    }

    result = retrieve(
        "OMEGA-912 是什么？",
        chunks,
        principal("public"),
        top_k=10,
    )

    assert other_tenant_chunk_ids.isdisjoint(result.scored_chunk_ids)
    assert all(chunk.tenant_id == "tenant-demo" for chunk in result.chunks)


@pytest.mark.parametrize(
    "forged_field",
    [
        "tenant_id",
        "user_id",
        "permission_group",
        "permission_groups",
        "allowed_permission_groups",
        "reviewer_id",
    ],
)
def test_request_rejects_forged_identity_and_authorization_fields(forged_field: str):
    payload = {
        "query": "RAG 为什么需要来源？",
        "collection_id": "demo",
        forged_field: "attacker-controlled",
    }

    with pytest.raises(RequestValidationError) as caught:
        parse_rag_query_request(payload)

    assert caught.value.status_code == 422
    assert caught.value.code == "forged_identity_fields"
    assert caught.value.fields == (forged_field,)


def test_valid_request_contains_business_fields_only():
    request = parse_rag_query_request(
        {"query": "RAG 为什么需要来源？", "collection_id": "demo", "top_k": 2}
    )

    assert request == RagQueryRequest(
        query="RAG 为什么需要来源？",
        collection_id="demo",
        top_k=2,
    )


def test_missing_authentication_and_scope_have_distinct_status_codes():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)
    request = RagQueryRequest("RAG 为什么需要来源？", "demo", 2)
    cache = RetrievalCache()

    with pytest.raises(AuthenticationRequired) as missing_auth:
        execute_retrieval(
            request,
            None,
            chunks,
            cache,
            collection_version="fixture-v1",
        )
    assert missing_auth.value.status_code == 401

    with pytest.raises(InsufficientScope) as missing_scope:
        execute_retrieval(
            request,
            principal("public", scopes=frozenset()),
            chunks,
            cache,
            collection_version="fixture-v1",
        )
    assert missing_scope.value.status_code == 403
    assert cache.entry_count == 0


def test_cache_cannot_cross_tenant_acl_or_acl_version():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)
    request = RagQueryRequest("客户 ZETA 为什么需要额外人工复核？", "demo", 3)
    cache = RetrievalCache()

    private_result = execute_retrieval(
        request,
        principal("public", "compliance_private"),
        chunks,
        cache,
        collection_version="fixture-v1",
    )
    public_result = execute_retrieval(
        request,
        principal("public"),
        chunks,
        cache,
        collection_version="fixture-v1",
    )
    changed_acl_result = execute_retrieval(
        request,
        principal("public", acl_version="acl-v2"),
        chunks,
        cache,
        collection_version="fixture-v1",
    )
    other_tenant_result = execute_retrieval(
        request,
        principal("public", tenant_id="tenant-other"),
        chunks,
        cache,
        collection_version="fixture-v1",
    )
    public_repeat = execute_retrieval(
        request,
        principal("public"),
        chunks,
        cache,
        collection_version="fixture-v1",
    )

    assert private_result.retrieval.chunks[0].document_id == "doc_compliance_private_001"
    assert all(
        chunk.document_id != "doc_compliance_private_001"
        for chunk in public_result.retrieval.chunks
    )
    assert len(
        {
            private_result.cache_key,
            public_result.cache_key,
            changed_acl_result.cache_key,
            other_tenant_result.cache_key,
        }
    ) == 4
    assert not private_result.cache_hit
    assert not public_result.cache_hit
    assert not changed_acl_result.cache_hit
    assert not other_tenant_result.cache_hit
    assert public_repeat.cache_hit
    assert public_repeat.cache_key == public_result.cache_key
    assert cache.entry_count == 4


def test_invalid_chunk_and_top_k_configuration_is_rejected():
    chunks = build_chunks(DOCUMENTS, chunk_size=80, overlap=10)

    with pytest.raises(ValueError, match="top_k"):
        retrieve("query", chunks, principal("public"), top_k=0)
