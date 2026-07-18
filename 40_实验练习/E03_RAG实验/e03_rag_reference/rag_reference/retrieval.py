from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
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


@dataclass(frozen=True)
class RetrievalResult:
    chunks: tuple[Chunk, ...]
    retrieval_ms: float
    authorized_search_space_size: int
    scored_chunk_ids: tuple[str, ...]


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


def retrieve(
    query: str,
    chunks: list[Chunk],
    principal: Principal,
    collection_id: str = "demo",
    top_k: int = 3,
) -> RetrievalResult:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    started = perf_counter_ns()
    authorized_chunks = [
        chunk
        for chunk in chunks
        if chunk.tenant_id == principal.tenant_id
        and chunk.collection_id == collection_id
        and chunk.permission_group in principal.effective_permission_groups
    ]
    if not authorized_chunks:
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000
        return RetrievalResult((), elapsed_ms, 0, ())

    tokenized_corpus = [tokenize(chunk.text) for chunk in authorized_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(
        zip(authorized_chunks, scores, strict=True),
        key=lambda item: (-float(item[1]), item[0].chunk_id),
    )
    selected = tuple(chunk for chunk, _score in ranked[:top_k])
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    return RetrievalResult(
        selected,
        elapsed_ms,
        len(authorized_chunks),
        tuple(chunk.chunk_id for chunk in authorized_chunks),
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
