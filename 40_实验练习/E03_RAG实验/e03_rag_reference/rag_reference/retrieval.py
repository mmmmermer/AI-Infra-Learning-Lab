from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from time import perf_counter_ns
from typing import Literal
import re

from rank_bm25 import BM25Okapi

from .corpus import Document, GoldQuery
from .security import Principal


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    permission_group: str
    text: str
    tenant_id: str
    collection_id: str
    source_id: str = "unknown"
    source_version: str = "unknown"
    document_sha256: str = "unknown"


@dataclass(frozen=True)
class RetrievalResult:
    chunks: tuple[Chunk, ...]
    retrieval_ms: float
    authorized_search_space_size: int
    scored_chunk_ids: tuple[str, ...]
    ranked_chunks: tuple["RankedChunk", ...] = ()


RetrievalMethod = Literal["lexical", "vector", "hybrid"]


# Auditable fixture features make paraphrase behavior deterministic. They are not a
# learned embedding and must not be used as a production semantic model.
SEMANTIC_FEATURES: tuple[tuple[str, ...], ...] = (
    ("来源", "引用", "证据", "无证", "断言", "cite", "source", "evidence"),
    ("rag", "chunk", "切分", "上下文", "检索"),
    ("sjf", "长任务", "副作用", "等待", "p95", "p99", "尾部"),
    ("卖方", "目的地", "出口", "合规", "贸易", "变更"),
    ("金融", "公告", "宏观", "供应链", "风险", "不确定性"),
)


@dataclass(frozen=True)
class RankedChunk:
    chunk: Chunk
    final_score: float
    lexical_score: float
    vector_score: float
    lexical_rank: int
    vector_rank: int


@dataclass(frozen=True)
class EvaluationRow:
    query_id: str
    recall_at_k: float
    reciprocal_rank: float
    retrieval_ms: float


def tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text.lower())
    if not normalized:
        return []
    if len(normalized) == 1:
        return [normalized]
    return [normalized[index : index + 2] for index in range(len(normalized) - 1)]


def chunk_document(document: Document, chunk_size: int, overlap: int) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    chunks: list[Chunk] = []
    step = chunk_size - overlap
    for index, start in enumerate(range(0, len(document.text), step)):
        text = document.text[start : start + chunk_size]
        if not text:
            break
        chunks.append(
            Chunk(
                chunk_id=f"{document.document_id}#chunk-{index:03d}",
                document_id=document.document_id,
                permission_group=document.permission_group,
                text=text,
                tenant_id=document.tenant_id,
                collection_id=document.collection_id,
                source_id=document.source_id,
                source_version=document.source_version,
                document_sha256=document.content_sha256,
            )
        )
        if start + chunk_size >= len(document.text):
            break
    return chunks


def build_chunks(documents: list[Document], chunk_size: int = 80, overlap: int = 10) -> list[Chunk]:
    return [
        chunk
        for document in documents
        for chunk in chunk_document(document, chunk_size=chunk_size, overlap=overlap)
    ]


def authorized_chunks(
    chunks: list[Chunk],
    principal: Principal,
    collection_id: str,
) -> list[Chunk]:
    """Return the only chunks that any ranker is allowed to inspect."""

    return [
        chunk
        for chunk in chunks
        if chunk.tenant_id == principal.tenant_id
        and chunk.collection_id == collection_id
        and chunk.permission_group in principal.effective_permission_groups
    ]


def _semantic_feature_vector(text: str) -> tuple[float, ...]:
    normalized = text.lower()
    return tuple(
        float(sum(normalized.count(term) for term in dimension))
        for dimension in SEMANTIC_FEATURES
    )


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not any(left) or not any(right):
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    query_norm = sqrt(sum(weight * weight for weight in left))
    document_norm = sqrt(sum(weight * weight for weight in right))
    if query_norm == 0 or document_norm == 0:
        return 0.0
    return dot_product / (query_norm * document_norm)


def rank_chunks(
    query: str,
    chunks: list[Chunk],
    principal: Principal,
    *,
    collection_id: str = "demo",
    method: RetrievalMethod = "lexical",
    rrf_k: int = 60,
) -> tuple[RankedChunk, ...]:
    """Rank an authorization-filtered set and retain every recomputable component."""

    if method not in {"lexical", "vector", "hybrid"}:
        raise ValueError(f"unsupported retrieval method: {method}")
    if rrf_k < 1:
        raise ValueError("rrf_k must be at least 1")

    candidates = authorized_chunks(chunks, principal, collection_id)
    if not candidates:
        return ()

    tokenized_corpus = [tokenize(chunk.text) for chunk in candidates]
    query_tokens = tokenize(query)
    bm25 = BM25Okapi(tokenized_corpus)
    lexical_scores = [float(score) for score in bm25.get_scores(query_tokens)]
    query_vector = _semantic_feature_vector(query)
    vector_scores = [
        _cosine(query_vector, _semantic_feature_vector(chunk.text))
        for chunk in candidates
    ]

    def component_ranks(scores: list[float]) -> dict[str, int]:
        ordered = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        return {chunk.chunk_id: rank for rank, (chunk, _score) in enumerate(ordered, 1)}

    lexical_ranks = component_ranks(lexical_scores)
    vector_ranks = component_ranks(vector_scores)
    ranked: list[RankedChunk] = []
    for chunk, lexical_score, vector_score in zip(
        candidates, lexical_scores, vector_scores, strict=True
    ):
        lexical_rank = lexical_ranks[chunk.chunk_id]
        vector_rank = vector_ranks[chunk.chunk_id]
        if method == "lexical":
            final_score = lexical_score
        elif method == "vector":
            final_score = vector_score
        else:
            final_score = (1.0 / (rrf_k + lexical_rank)) + (
                1.0 / (rrf_k + vector_rank)
            )
        ranked.append(
            RankedChunk(
                chunk=chunk,
                final_score=final_score,
                lexical_score=lexical_score,
                vector_score=vector_score,
                lexical_rank=lexical_rank,
                vector_rank=vector_rank,
            )
        )
    return tuple(
        sorted(ranked, key=lambda row: (-row.final_score, row.chunk.chunk_id))
    )


def retrieve(
    query: str,
    chunks: list[Chunk],
    principal: Principal,
    collection_id: str = "demo",
    top_k: int = 3,
    method: RetrievalMethod = "lexical",
    rrf_k: int = 60,
) -> RetrievalResult:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    started = perf_counter_ns()
    candidates = authorized_chunks(chunks, principal, collection_id)
    if not candidates:
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        return RetrievalResult((), elapsed_ms, 0, (), ())

    ranked = rank_chunks(
        query,
        chunks,
        principal,
        collection_id=collection_id,
        method=method,
        rrf_k=rrf_k,
    )
    selected = tuple(row.chunk for row in ranked[:top_k])
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    return RetrievalResult(
        selected,
        elapsed_ms,
        len(candidates),
        tuple(chunk.chunk_id for chunk in candidates),
        ranked,
    )


def recall_at_k(retrieved: tuple[Chunk, ...], expected_document_ids: frozenset[str]) -> float:
    if not expected_document_ids:
        return 1.0
    retrieved_ids = {chunk.document_id for chunk in retrieved}
    return len(retrieved_ids.intersection(expected_document_ids)) / len(expected_document_ids)


def reciprocal_rank(retrieved: tuple[Chunk, ...], expected_document_ids: frozenset[str]) -> float:
    for rank, chunk in enumerate(retrieved, start=1):
        if chunk.document_id in expected_document_ids:
            return 1.0 / rank
    return 0.0


def evaluate_queries(
    queries: list[GoldQuery],
    chunks: list[Chunk],
    top_k: int = 3,
) -> list[EvaluationRow]:
    rows: list[EvaluationRow] = []
    for query in queries:
        principal = Principal(
            tenant_id=query.tenant_id,
            user_id=f"evaluation:{query.query_id}",
            scopes=frozenset({"rag:query"}),
            effective_permission_groups=query.allowed_groups,
            acl_version="fixture-v1",
        )
        result = retrieve(
            query.query,
            chunks,
            principal,
            collection_id=query.collection_id,
            top_k=top_k,
        )
        rows.append(
            EvaluationRow(
                query_id=query.query_id,
                recall_at_k=recall_at_k(result.chunks, query.expected_document_ids),
                reciprocal_rank=reciprocal_rank(result.chunks, query.expected_document_ids),
                retrieval_ms=result.retrieval_ms,
            )
        )
    return rows
