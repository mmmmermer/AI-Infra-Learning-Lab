from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json

from .retrieval import Chunk, RetrievalResult, retrieve
from .security import Principal, require_scope


IDENTITY_FIELDS = frozenset(
    {
        "user_id",
        "tenant_id",
        "permission_group",
        "permission_groups",
        "allowed_permission_groups",
        "reviewer_id",
    }
)
REQUEST_FIELDS = frozenset({"query", "collection_id", "top_k"})


class RequestValidationError(ValueError):
    status_code = 422

    def __init__(self, code: str, fields: set[str] | frozenset[str]) -> None:
        self.code = code
        self.fields = tuple(sorted(fields))
        super().__init__(f"{code}:{','.join(self.fields)}")


@dataclass(frozen=True)
class RagQueryRequest:
    query: str
    collection_id: str
    top_k: int = 3


@dataclass(frozen=True)
class ServiceResult:
    retrieval: RetrievalResult
    cache_key: str
    cache_hit: bool


@dataclass(frozen=True)
class _CacheEntry:
    result: RetrievalResult
    tenant_id: str
    collection_id: str
    collection_version: str


class RetrievalCache:
    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> RetrievalResult | None:
        entry = self._entries.get(key)
        return None if entry is None else entry.result

    def put(
        self,
        key: str,
        result: RetrievalResult,
        *,
        tenant_id: str,
        collection_id: str,
        collection_version: str,
    ) -> None:
        self._entries[key] = _CacheEntry(
            result=result,
            tenant_id=tenant_id,
            collection_id=collection_id,
            collection_version=collection_version,
        )

    def invalidate_collection(self, tenant_id: str, collection_id: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if entry.tenant_id == tenant_id and entry.collection_id == collection_id
        ]
        for key in keys:
            del self._entries[key]
        return len(keys)

    @property
    def entry_count(self) -> int:
        return len(self._entries)


def parse_rag_query_request(payload: Mapping[str, object]) -> RagQueryRequest:
    supplied_fields = set(payload)
    forged_fields = supplied_fields.intersection(IDENTITY_FIELDS)
    if forged_fields:
        raise RequestValidationError("forged_identity_fields", forged_fields)

    unknown_fields = supplied_fields.difference(REQUEST_FIELDS)
    if unknown_fields:
        raise RequestValidationError("unknown_fields", unknown_fields)

    missing_fields = {field for field in ("query", "collection_id") if field not in payload}
    if missing_fields:
        raise RequestValidationError("missing_fields", missing_fields)

    query = payload["query"]
    collection_id = payload["collection_id"]
    top_k = payload.get("top_k", 3)
    malformed_fields: set[str] = set()
    if not isinstance(query, str) or not query.strip():
        malformed_fields.add("query")
    if not isinstance(collection_id, str) or not collection_id.strip():
        malformed_fields.add("collection_id")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        malformed_fields.add("top_k")
    if malformed_fields:
        raise RequestValidationError("malformed_fields", malformed_fields)

    return RagQueryRequest(query=query.strip(), collection_id=collection_id.strip(), top_k=top_k)


def build_cache_key(
    request: RagQueryRequest,
    principal: Principal,
    *,
    collection_version: str,
    retrieval_version: str,
) -> str:
    payload = json.dumps(
        {
            "tenant_id": principal.tenant_id,
            "acl_fingerprint": principal.acl_fingerprint(),
            "collection_id": request.collection_id,
            "collection_version": collection_version,
            "retrieval_version": retrieval_version,
            "query": request.query,
            "top_k": request.top_k,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def execute_retrieval(
    request: RagQueryRequest,
    principal: Principal | None,
    chunks: list[Chunk],
    cache: RetrievalCache,
    *,
    collection_version: str,
    retrieval_version: str = "bm25-bigram-v1",
) -> ServiceResult:
    verified_principal = require_scope(principal, "rag:query")
    cache_key = build_cache_key(
        request,
        verified_principal,
        collection_version=collection_version,
        retrieval_version=retrieval_version,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        _assert_result_is_authorized(cached, request, verified_principal)
        return ServiceResult(cached, cache_key, True)

    result = retrieve(
        request.query,
        chunks,
        verified_principal,
        collection_id=request.collection_id,
        top_k=request.top_k,
    )
    _assert_result_is_authorized(result, request, verified_principal)
    cache.put(
        cache_key,
        result,
        tenant_id=verified_principal.tenant_id,
        collection_id=request.collection_id,
        collection_version=collection_version,
    )
    return ServiceResult(result, cache_key, False)


def _assert_result_is_authorized(
    result: RetrievalResult,
    request: RagQueryRequest,
    principal: Principal,
) -> None:
    for chunk in result.chunks:
        if (
            chunk.tenant_id != principal.tenant_id
            or chunk.collection_id != request.collection_id
            or chunk.permission_group not in principal.effective_permission_groups
        ):
            raise RuntimeError("unauthorized_chunk_in_retrieval_result")
