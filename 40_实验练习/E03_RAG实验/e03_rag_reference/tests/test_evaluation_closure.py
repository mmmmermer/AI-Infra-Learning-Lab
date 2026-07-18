import json
from pathlib import Path

import pytest

from rag_reference.corpus import DOCUMENTS, GOLD_QUERIES, GoldQuery, Document
from rag_reference.evaluation import (
    METHODS,
    compare_retrieval_methods,
    recompute_diagnostic_from_evidence,
    write_comparison_report,
)
from rag_reference.retrieval import build_chunks


FIXTURES = Path(__file__).parent / "fixtures"


def load_gold_queries() -> list[GoldQuery]:
    rows = json.loads((FIXTURES / "golden_queries.json").read_text(encoding="utf-8"))
    return [
        GoldQuery(
            query_id=row["query_id"],
            query=row["query"],
            allowed_groups=frozenset(row["allowed_groups"]),
            expected_document_ids=frozenset(row["expected_document_ids"]),
        )
        for row in rows
    ]


def test_same_golden_set_compares_lexical_vector_and_hybrid_with_raw_evidence():
    queries = load_gold_queries()
    assert queries == GOLD_QUERIES
    report = compare_retrieval_methods(
        queries,
        build_chunks(DOCUMENTS, chunk_size=80, overlap=10),
        top_k=3,
        rrf_k=60,
    )

    assert report.methods == METHODS == ("lexical", "vector", "hybrid")
    assert report.query_ids == tuple(query.query_id for query in queries)
    assert {
        (row.query_id, row.method) for row in report.diagnostics
    } == {
        (query.query_id, method) for query in queries for method in METHODS
    }
    assert report.raw_rankings
    assert len(report.corpus_fingerprint) == 64
    assert len(report.query_set_fingerprint) == 64

    q5 = {
        row.method: row.failure_class
        for row in report.diagnostics
        if row.query_id == "Q5"
    }
    assert q5 == {
        "lexical": "zero_retrieval_signal",
        "vector": "passed",
        "hybrid": "relevant_not_ranked_first",
    }

    for query in queries:
        for method in METHODS:
            expected = next(
                row
                for row in report.diagnostics
                if row.query_id == query.query_id and row.method == method
            )
            recall, reciprocal_rank, ndcg = recompute_diagnostic_from_evidence(
                report, query, method
            )
            assert recall == pytest.approx(expected.recall_at_k)
            assert reciprocal_rank == pytest.approx(expected.reciprocal_rank)
            assert ndcg == pytest.approx(expected.ndcg_at_k)


def test_hybrid_rrf_score_is_recomputable_from_component_ranks():
    report = compare_retrieval_methods(
        load_gold_queries(),
        build_chunks(DOCUMENTS, chunk_size=80, overlap=10),
        top_k=3,
        rrf_k=60,
    )

    for row in (item for item in report.raw_rankings if item.method == "hybrid"):
        recomputed = (1 / (report.rrf_k + row.lexical_rank)) + (
            1 / (report.rrf_k + row.vector_rank)
        )
        assert row.final_score == pytest.approx(recomputed)


def test_report_is_stable_and_excludes_raw_corpus_text(tmp_path: Path):
    report = compare_retrieval_methods(
        load_gold_queries(), build_chunks(DOCUMENTS), top_k=3
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_comparison_report(report, first)
    write_comparison_report(report, second)

    assert first.read_bytes() == second.read_bytes()
    serialized = first.read_text(encoding="utf-8")
    assert DOCUMENTS[0].text not in serialized
    assert "retrieval_ms" not in serialized


def test_failed_query_has_a_deterministic_failure_class():
    documents = [
        Document("a-noise", "public", "completely unrelated material"),
        Document("z-relevant", "public", "the expected evidence"),
    ]
    query = GoldQuery(
        "FAIL-001",
        "unseen vocabulary xyzzy",
        frozenset({"public"}),
        frozenset({"z-relevant"}),
    )

    report = compare_retrieval_methods(
        [query], build_chunks(documents, chunk_size=200, overlap=0), top_k=1
    )
    lexical = next(row for row in report.diagnostics if row.method == "lexical")

    assert lexical.recall_at_k == 0
    assert lexical.failure_class == "zero_retrieval_signal"


def test_zero_signal_tie_break_cannot_turn_an_accidental_hit_into_a_pass():
    documents = [
        Document("a-relevant", "public", "the expected evidence"),
        Document("z-noise", "public", "completely unrelated material"),
    ]
    query = GoldQuery(
        "ZERO-TIE",
        "unseen vocabulary xyzzy",
        frozenset({"public"}),
        frozenset({"a-relevant"}),
    )

    report = compare_retrieval_methods(
        [query], build_chunks(documents, chunk_size=200, overlap=0), top_k=1
    )

    assert all(row.recall_at_k == 1 for row in report.diagnostics)
    assert {
        row.method: row.failure_class for row in report.diagnostics
    } == {
        "lexical": "zero_retrieval_signal",
        "vector": "zero_retrieval_signal",
        "hybrid": "zero_retrieval_signal",
    }


def test_ndcg_does_not_count_duplicate_chunks_as_extra_relevant_documents():
    document = Document(
        "doc-relevant",
        "public",
        "relevant evidence repeated across enough text to create several chunks",
    )
    query = GoldQuery(
        "DUP-001",
        "relevant evidence",
        frozenset({"public"}),
        frozenset({"doc-relevant"}),
    )

    report = compare_retrieval_methods(
        [query], build_chunks([document], chunk_size=20, overlap=5), top_k=3
    )

    assert all(0 <= row.ndcg_at_k <= 1 for row in report.diagnostics)


def test_failure_taxonomy_separates_data_acl_cutoff_and_partial_recall():
    missing = compare_retrieval_methods(
        [
            GoldQuery(
                "MISSING",
                "source evidence",
                frozenset({"public"}),
                frozenset({"doc-absent"}),
            )
        ],
        build_chunks([Document("doc-present", "public", "source evidence")]),
        top_k=1,
    )
    assert missing.diagnostics[0].failure_class == "gold_missing_from_corpus"

    outside_acl = compare_retrieval_methods(
        [
            GoldQuery(
                "ACL",
                "source evidence",
                frozenset({"public"}),
                frozenset({"doc-private"}),
            )
        ],
        build_chunks([Document("doc-private", "private", "source evidence")]),
        top_k=1,
    )
    assert outside_acl.diagnostics[0].failure_class == "gold_outside_authorized_scope"

    mixed_acl = compare_retrieval_methods(
        [
            GoldQuery(
                "MIXED-ACL",
                "source evidence",
                frozenset({"public"}),
                frozenset({"doc-public", "doc-private"}),
            )
        ],
        build_chunks(
            [
                Document("doc-public", "public", "source evidence"),
                Document("doc-private", "private", "source evidence"),
            ]
        ),
        top_k=2,
    )
    assert all(
        row.failure_class == "gold_outside_authorized_scope"
        for row in mixed_acl.diagnostics
    )

    cutoff = compare_retrieval_methods(
        [
            GoldQuery(
                "CUTOFF",
                "source evidence",
                frozenset({"public"}),
                frozenset({"z-relevant"}),
            )
        ],
        build_chunks(
            [
                Document("a-noise", "public", "source evidence source evidence"),
                Document("z-relevant", "public", "source evidence"),
            ]
        ),
        top_k=1,
    )
    cutoff_vector = next(row for row in cutoff.diagnostics if row.method == "vector")
    assert cutoff_vector.failure_class == "relevant_below_cutoff"

    partial = compare_retrieval_methods(
        [
            GoldQuery(
                "PARTIAL",
                "source evidence",
                frozenset({"public"}),
                frozenset({"a-relevant", "z-relevant"}),
            )
        ],
        build_chunks(
            [
                Document("a-relevant", "public", "source evidence"),
                Document("z-relevant", "public", "source evidence"),
            ]
        ),
        top_k=1,
    )
    assert partial.diagnostics[0].failure_class == "partial_recall"
