from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event, Lock
from time import sleep

import pytest

from e06_reference import (
    AuthorizedScope,
    AuthorizationInvariantError,
    MemoryCacheBackend,
    Principal,
    RetrievalRequest,
    RetrievalResult,
    SafeRetrievalCache,
    UnavailableCacheBackend,
    make_retrieval_cache_key,
)


PUBLIC = Principal("tenant-a", "user-public", ("public",), "acl-v1")
COMPLIANCE = Principal(
    "tenant-a",
    "user-compliance",
    ("public", "compliance_private"),
    "acl-v1",
)
REQUEST = RetrievalRequest("why sources", "docs", 2)


def scope_for(
    principal: Principal,
    request: RetrievalRequest,
    *,
    document_version: str = "docs-v1",
) -> AuthorizedScope:
    source_ids = ["doc-public"]
    if "compliance_private" in principal.permission_groups:
        source_ids.append("doc-private")
    return AuthorizedScope(
        collection_id=request.collection_id,
        source_ids=tuple(source_ids),
        document_version=document_version,
        index_version="index-v1",
        embedding_model_version="embed-v1",
        retriever_version="bm25-v1",
    )


def public_result(scope: AuthorizedScope, request: RetrievalRequest) -> RetrievalResult:
    return RetrievalResult("answer", scope.source_ids[: request.top_k])


def test_cache_key_isolated_by_owner_acl_and_content_version():
    backend = MemoryCacheBackend()
    cache = SafeRetrievalCache(backend)
    versions = {"document": "docs-v1"}
    compute_calls = 0

    def authorize(principal, request):
        return scope_for(
            principal,
            request,
            document_version=versions["document"],
        )

    def compute(scope, request):
        nonlocal compute_calls
        compute_calls += 1
        return public_result(scope, request)

    cold = cache.retrieve(PUBLIC, REQUEST, authorize=authorize, compute=compute)
    warm = cache.retrieve(PUBLIC, REQUEST, authorize=authorize, compute=compute)
    wider_acl = cache.retrieve(COMPLIANCE, REQUEST, authorize=authorize, compute=compute)
    versions["document"] = "docs-v2"
    updated = cache.retrieve(PUBLIC, REQUEST, authorize=authorize, compute=compute)

    assert cold.cache_hit is False
    assert warm.cache_hit is True
    assert wider_acl.cache_hit is False
    assert updated.cache_hit is False
    assert len({cold.cache_key, wider_acl.cache_key, updated.cache_key}) == 3
    assert warm.result.source_ids == ("doc-public",)
    assert compute_calls == 3


def test_ttl_expiry_and_bounded_lru_eviction_are_observable():
    now = [0.0]
    backend = MemoryCacheBackend(max_entries=1, clock=lambda: now[0])
    cache = SafeRetrievalCache(backend, ttl_seconds=10)
    compute_calls = 0

    def compute(scope, request):
        nonlocal compute_calls
        compute_calls += 1
        return public_result(scope, request)

    authorize = lambda principal, request: scope_for(principal, request)
    cache.retrieve(PUBLIC, REQUEST, authorize=authorize, compute=compute)
    assert cache.retrieve(
        PUBLIC, REQUEST, authorize=authorize, compute=compute
    ).cache_hit

    second = RetrievalRequest("different", "docs", 2)
    cache.retrieve(PUBLIC, second, authorize=authorize, compute=compute)
    assert backend.entry_count() == 1
    assert not cache.retrieve(
        PUBLIC, REQUEST, authorize=authorize, compute=compute
    ).cache_hit

    now[0] = 11.0
    assert not cache.retrieve(
        PUBLIC, REQUEST, authorize=authorize, compute=compute
    ).cache_hit
    assert compute_calls == 4


def test_corrupt_or_over_scoped_cache_value_is_deleted_and_recomputed():
    backend = MemoryCacheBackend()
    cache = SafeRetrievalCache(backend)
    scope = scope_for(PUBLIC, REQUEST)
    key = make_retrieval_cache_key(PUBLIC, REQUEST, scope)
    backend.raw_set_for_test(
        key,
        json.dumps(
            {
                "schema_version": 1,
                "answer": "poisoned",
                "source_ids": ["doc-private"],
            }
        ),
    )

    outcome = cache.retrieve(
        PUBLIC,
        REQUEST,
        authorize=lambda principal, request: scope,
        compute=public_result,
    )

    assert outcome.cache_hit is False
    assert outcome.cache_value_invalid is True
    assert outcome.result.source_ids == ("doc-public",)
    assert cache.retrieve(
        PUBLIC,
        REQUEST,
        authorize=lambda principal, request: scope,
        compute=public_result,
    ).cache_hit


def test_backend_outage_falls_back_only_after_authorization():
    cache = SafeRetrievalCache(UnavailableCacheBackend())
    calls: list[str] = []

    def authorize(principal, request):
        calls.append("authorize")
        return scope_for(principal, request)

    def compute(scope, request):
        calls.append("compute")
        return public_result(scope, request)

    outcome = cache.retrieve(PUBLIC, REQUEST, authorize=authorize, compute=compute)

    assert calls == ["authorize", "compute"]
    assert outcome.cache_unavailable is True
    assert outcome.cache_hit is False
    assert outcome.result.source_ids == ("doc-public",)


def test_compute_cannot_return_a_source_outside_authorized_scope():
    cache = SafeRetrievalCache(MemoryCacheBackend())

    with pytest.raises(AuthorizationInvariantError, match="escaped authorized scope"):
        cache.retrieve(
            PUBLIC,
            REQUEST,
            authorize=lambda principal, request: scope_for(principal, request),
            compute=lambda scope, request: RetrievalResult(
                "bad", ("doc-public", "doc-private")
            ),
        )


def test_concurrent_miss_runs_one_compute_and_shares_the_flight():
    backend = MemoryCacheBackend()
    cache = SafeRetrievalCache(backend)
    callers = 8
    barrier = Barrier(callers)
    compute_started = Event()
    call_lock = Lock()
    compute_calls = 0

    def compute(scope, request):
        nonlocal compute_calls
        with call_lock:
            compute_calls += 1
        compute_started.set()
        sleep(0.05)
        return public_result(scope, request)

    def invoke():
        barrier.wait()
        return cache.retrieve(
            PUBLIC,
            REQUEST,
            authorize=lambda principal, request: scope_for(principal, request),
            compute=compute,
        )

    with ThreadPoolExecutor(max_workers=callers) as executor:
        futures = [executor.submit(invoke) for _ in range(callers)]
        assert compute_started.wait(timeout=2)
        outcomes = [future.result(timeout=2) for future in futures]

    assert compute_calls == 1
    assert {outcome.result for outcome in outcomes} == {
        RetrievalResult("answer", ("doc-public",))
    }
    assert sum(outcome.singleflight_shared for outcome in outcomes) >= callers - 1
