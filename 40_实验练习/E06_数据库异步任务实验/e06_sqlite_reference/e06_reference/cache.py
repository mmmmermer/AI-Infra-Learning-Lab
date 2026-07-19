from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from threading import Lock
from time import monotonic
from typing import Protocol


CACHE_SCHEMA_VERSION = 1


class CacheBackendUnavailable(RuntimeError):
    """Raised by an adapter when its cache service cannot be used."""


class AuthorizationInvariantError(RuntimeError):
    """Raised when a retriever or cached value escapes its authorized scope."""


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    permission_groups: tuple[str, ...]
    acl_version: str

    def __post_init__(self) -> None:
        groups = tuple(sorted(set(self.permission_groups)))
        if not self.tenant_id or not self.user_id or not self.acl_version:
            raise ValueError("principal identity and acl_version must be non-empty")
        if not groups or any(not group for group in groups):
            raise ValueError("permission_groups must contain non-empty values")
        object.__setattr__(self, "permission_groups", groups)

    @property
    def acl_fingerprint(self) -> str:
        return _canonical_hash(
            {
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "permission_groups": self.permission_groups,
                "acl_version": self.acl_version,
            }
        )


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    collection_id: str
    top_k: int
    filters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.query.strip() or not self.collection_id:
            raise ValueError("query and collection_id must be non-empty")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        object.__setattr__(self, "filters", tuple(sorted(self.filters)))


@dataclass(frozen=True)
class AuthorizedScope:
    collection_id: str
    source_ids: tuple[str, ...]
    document_version: str
    index_version: str
    embedding_model_version: str
    retriever_version: str

    def __post_init__(self) -> None:
        source_ids = tuple(sorted(set(self.source_ids)))
        versions = (
            self.collection_id,
            self.document_version,
            self.index_version,
            self.embedding_model_version,
            self.retriever_version,
        )
        if any(not value for value in versions):
            raise ValueError("authorized scope versions must be non-empty")
        object.__setattr__(self, "source_ids", source_ids)

    @property
    def source_fingerprint(self) -> str:
        return _canonical_hash(self.source_ids)


@dataclass(frozen=True)
class RetrievalResult:
    answer: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str):
            raise TypeError("answer must be a string")
        if any(not isinstance(source_id, str) or not source_id for source_id in self.source_ids):
            raise ValueError("source_ids must contain non-empty strings")


@dataclass(frozen=True)
class CacheOutcome:
    result: RetrievalResult
    cache_key: str
    cache_hit: bool
    cache_unavailable: bool
    cache_value_invalid: bool
    singleflight_shared: bool = False


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryCacheBackend:
    """A bounded LRU/TTL backend used for deterministic reference tests."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self.clock = clock
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self.clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._entries[key] = (self.clock() + ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def raw_set_for_test(self, key: str, value: str, ttl_seconds: int = 60) -> None:
        self.set(key, value, ttl_seconds)

    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)


class UnavailableCacheBackend:
    """A fault-injection adapter that models a normalized Redis outage."""

    def get(self, key: str) -> str | None:
        raise CacheBackendUnavailable("cache backend unavailable")

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        raise CacheBackendUnavailable("cache backend unavailable")

    def delete(self, key: str) -> None:
        raise CacheBackendUnavailable("cache backend unavailable")


class SafeRetrievalCache:
    def __init__(self, backend: CacheBackend, *, ttl_seconds: int = 300) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.backend = backend
        self.ttl_seconds = ttl_seconds
        self._flights: dict[str, Future[CacheOutcome]] = {}
        self._flights_lock = Lock()

    def retrieve(
        self,
        principal: Principal,
        request: RetrievalRequest,
        *,
        authorize: Callable[[Principal, RetrievalRequest], AuthorizedScope],
        compute: Callable[[AuthorizedScope, RetrievalRequest], RetrievalResult],
    ) -> CacheOutcome:
        # Authorization deliberately precedes every cache operation, including hits.
        scope = authorize(principal, request)
        if scope.collection_id != request.collection_id:
            raise AuthorizationInvariantError("authorization returned the wrong collection")
        key = make_retrieval_cache_key(principal, request, scope)

        cached, unavailable, invalid = self._read_validated(key, scope)
        if cached is not None:
            return CacheOutcome(cached, key, True, unavailable, invalid)

        with self._flights_lock:
            future = self._flights.get(key)
            leader = future is None
            if leader:
                future = Future()
                self._flights[key] = future

        assert future is not None
        if not leader:
            return replace(future.result(), singleflight_shared=True)

        try:
            # A second read closes the miss-to-flight race without holding a global lock.
            cached, second_unavailable, second_invalid = self._read_validated(key, scope)
            unavailable = unavailable or second_unavailable
            invalid = invalid or second_invalid
            if cached is not None:
                outcome = CacheOutcome(cached, key, True, unavailable, invalid)
            else:
                result = compute(scope, request)
                self._assert_authorized_result(result, scope)
                try:
                    self.backend.set(key, _encode_result(result), self.ttl_seconds)
                except CacheBackendUnavailable:
                    unavailable = True
                outcome = CacheOutcome(result, key, False, unavailable, invalid)
            future.set_result(outcome)
            return outcome
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._flights_lock:
                if self._flights.get(key) is future:
                    del self._flights[key]

    def _read_validated(
        self, key: str, scope: AuthorizedScope
    ) -> tuple[RetrievalResult | None, bool, bool]:
        try:
            value = self.backend.get(key)
        except CacheBackendUnavailable:
            return None, True, False
        if value is None:
            return None, False, False

        try:
            result = _decode_result(value)
            self._assert_authorized_result(result, scope)
        except (ValueError, TypeError, AuthorizationInvariantError, json.JSONDecodeError):
            try:
                self.backend.delete(key)
            except CacheBackendUnavailable:
                return None, True, True
            return None, False, True
        return result, False, False

    @staticmethod
    def _assert_authorized_result(
        result: RetrievalResult, scope: AuthorizedScope
    ) -> None:
        unauthorized = set(result.source_ids).difference(scope.source_ids)
        if unauthorized:
            raise AuthorizationInvariantError(
                f"retrieval result escaped authorized scope: {sorted(unauthorized)}"
            )


def make_retrieval_cache_key(
    principal: Principal,
    request: RetrievalRequest,
    scope: AuthorizedScope,
) -> str:
    context = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "tenant_id": principal.tenant_id,
        "user_id": principal.user_id,
        "permission_groups": principal.permission_groups,
        "acl_version": principal.acl_version,
        "acl_fingerprint": principal.acl_fingerprint,
        "collection_id": request.collection_id,
        "document_version": scope.document_version,
        "index_version": scope.index_version,
        "embedding_model_version": scope.embedding_model_version,
        "retriever_version": scope.retriever_version,
        "source_fingerprint": scope.source_fingerprint,
        "filters": request.filters,
        "top_k": request.top_k,
        "query_hash": _canonical_hash(request.query.strip()),
    }
    return f"retrieval:v{CACHE_SCHEMA_VERSION}:{_canonical_hash(context)}"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _encode_result(result: RetrievalResult) -> str:
    return json.dumps(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "answer": result.answer,
            "source_ids": result.source_ids,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_result(value: str) -> RetrievalResult:
    payload = json.loads(value)
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "answer",
        "source_ids",
    }:
        raise ValueError("cache value has an invalid object shape")
    if payload["schema_version"] != CACHE_SCHEMA_VERSION:
        raise ValueError("cache value has an unsupported schema version")
    if not isinstance(payload["answer"], str) or not isinstance(payload["source_ids"], list):
        raise TypeError("cache value fields have invalid types")
    if not all(isinstance(source_id, str) for source_id in payload["source_ids"]):
        raise TypeError("cache source_ids must be strings")
    return RetrievalResult(payload["answer"], tuple(payload["source_ids"]))
