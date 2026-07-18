from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import log2
from pathlib import Path

from .corpus import GoldQuery
from .retrieval import (
    Chunk,
    RetrievalMethod,
    authorized_chunks,
    rank_chunks,
    recall_at_k,
    reciprocal_rank,
)
from .security import Principal


METHODS: tuple[RetrievalMethod, ...] = ("lexical", "vector", "hybrid")


@dataclass(frozen=True)
class RankingEvidence:
    query_id: str
    method: RetrievalMethod
    final_rank: int
    chunk_id: str
    document_id: str
    final_score: float
    lexical_score: float
    vector_score: float
    lexical_rank: int
    vector_rank: int


@dataclass(frozen=True)
class QueryDiagnostic:
    query_id: str
    method: RetrievalMethod
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    failure_class: str


@dataclass(frozen=True)
class ComparisonReport:
    schema_version: str
    corpus_fingerprint: str
    query_set_fingerprint: str
    query_ids: tuple[str, ...]
    methods: tuple[RetrievalMethod, ...]
    top_k: int
    rrf_k: int
    diagnostics: tuple[QueryDiagnostic, ...]
    raw_rankings: tuple[RankingEvidence, ...]


def ndcg_at_k(
    ranked_document_ids: list[str],
    expected_document_ids: frozenset[str],
    top_k: int,
) -> float:
    seen_relevant: set[str] = set()
    gains: list[float] = []
    for document_id in ranked_document_ids[:top_k]:
        is_new_relevant = (
            document_id in expected_document_ids
            and document_id not in seen_relevant
        )
        gains.append(1.0 if is_new_relevant else 0.0)
        if is_new_relevant:
            seen_relevant.add(document_id)
    dcg = sum(gain / log2(rank + 1) for rank, gain in enumerate(gains, 1))
    ideal_relevant = min(len(expected_document_ids), top_k)
    if ideal_relevant == 0:
        return 1.0
    ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_relevant + 1))
    return dcg / ideal_dcg


def _failure_class(
    query: GoldQuery,
    chunks: list[Chunk],
    ranked_rows: tuple,
    top_k: int,
    method: RetrievalMethod,
) -> str:
    corpus_document_ids = {chunk.document_id for chunk in chunks}
    if not query.expected_document_ids.issubset(corpus_document_ids):
        return "gold_missing_from_corpus"

    principal = _principal_for(query)
    authorized_document_ids = {
        chunk.document_id
        for chunk in authorized_chunks(chunks, principal, query.collection_id)
    }
    if not query.expected_document_ids.issubset(authorized_document_ids):
        return "gold_outside_authorized_scope"

    def has_signal(row) -> bool:
        if method == "lexical":
            return abs(row.lexical_score) > 1e-15
        if method == "vector":
            return row.vector_score > 1e-15
        return abs(row.lexical_score) > 1e-15 or row.vector_score > 1e-15

    positive_signal = any(
        has_signal(row) and row.chunk.document_id in query.expected_document_ids
        for row in ranked_rows
    )
    if not positive_signal:
        return "zero_retrieval_signal"

    selected = tuple(row.chunk for row in ranked_rows[:top_k])
    recall = recall_at_k(selected, query.expected_document_ids)
    rr = reciprocal_rank(selected, query.expected_document_ids)
    if recall == 0:
        return "relevant_below_cutoff"
    if recall < 1:
        return "partial_recall"
    if rr < 1:
        return "relevant_not_ranked_first"
    return "passed"


def _principal_for(query: GoldQuery) -> Principal:
    return Principal(
        tenant_id=query.tenant_id,
        user_id=f"evaluation:{query.query_id}",
        scopes=frozenset({"rag:query"}),
        effective_permission_groups=query.allowed_groups,
        acl_version="fixture-v1",
    )


def _corpus_fingerprint(chunks: list[Chunk]) -> str:
    payload = [
        {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "tenant_id": chunk.tenant_id,
            "collection_id": chunk.collection_id,
            "permission_group": chunk.permission_group,
            "text_sha256": sha256(chunk.text.encode("utf-8")).hexdigest(),
        }
        for chunk in sorted(chunks, key=lambda item: item.chunk_id)
    ]
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _query_set_fingerprint(queries: list[GoldQuery]) -> str:
    payload = [
        {
            "query_id": query.query_id,
            "query": query.query,
            "tenant_id": query.tenant_id,
            "collection_id": query.collection_id,
            "allowed_groups": sorted(query.allowed_groups),
            "expected_document_ids": sorted(query.expected_document_ids),
        }
        for query in queries
    ]
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def compare_retrieval_methods(
    queries: list[GoldQuery],
    chunks: list[Chunk],
    *,
    top_k: int = 3,
    rrf_k: int = 60,
) -> ComparisonReport:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    diagnostics: list[QueryDiagnostic] = []
    evidence: list[RankingEvidence] = []
    for query in queries:
        principal = _principal_for(query)
        for method in METHODS:
            ranked = rank_chunks(
                query.query,
                chunks,
                principal,
                collection_id=query.collection_id,
                method=method,
                rrf_k=rrf_k,
            )
            for final_rank, row in enumerate(ranked, 1):
                evidence.append(
                    RankingEvidence(
                        query_id=query.query_id,
                        method=method,
                        final_rank=final_rank,
                        chunk_id=row.chunk.chunk_id,
                        document_id=row.chunk.document_id,
                        final_score=row.final_score,
                        lexical_score=row.lexical_score,
                        vector_score=row.vector_score,
                        lexical_rank=row.lexical_rank,
                        vector_rank=row.vector_rank,
                    )
                )
            selected = tuple(row.chunk for row in ranked[:top_k])
            diagnostics.append(
                QueryDiagnostic(
                    query_id=query.query_id,
                    method=method,
                    recall_at_k=recall_at_k(selected, query.expected_document_ids),
                    reciprocal_rank=reciprocal_rank(
                        selected, query.expected_document_ids
                    ),
                    ndcg_at_k=ndcg_at_k(
                        [row.chunk.document_id for row in ranked],
                        query.expected_document_ids,
                        top_k,
                    ),
                    failure_class=_failure_class(
                        query, chunks, ranked, top_k, method
                    ),
                )
            )
    return ComparisonReport(
        schema_version="e03-retrieval-comparison-v1",
        corpus_fingerprint=_corpus_fingerprint(chunks),
        query_set_fingerprint=_query_set_fingerprint(queries),
        query_ids=tuple(query.query_id for query in queries),
        methods=METHODS,
        top_k=top_k,
        rrf_k=rrf_k,
        diagnostics=tuple(diagnostics),
        raw_rankings=tuple(evidence),
    )


def recompute_diagnostic_from_evidence(
    report: ComparisonReport,
    query: GoldQuery,
    method: RetrievalMethod,
) -> tuple[float, float, float]:
    rows = sorted(
        (
            row
            for row in report.raw_rankings
            if row.query_id == query.query_id and row.method == method
        ),
        key=lambda row: row.final_rank,
    )
    selected_ids = [row.document_id for row in rows[: report.top_k]]
    retrieved = tuple(
        _EvidenceChunk(document_id=document_id) for document_id in selected_ids
    )
    return (
        recall_at_k(retrieved, query.expected_document_ids),
        reciprocal_rank(retrieved, query.expected_document_ids),
        ndcg_at_k(
            [row.document_id for row in rows],
            query.expected_document_ids,
            report.top_k,
        ),
    )


@dataclass(frozen=True)
class _EvidenceChunk:
    document_id: str


def write_comparison_report(report: ComparisonReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
