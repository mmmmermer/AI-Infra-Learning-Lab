import argparse
from pathlib import Path

from rag_reference.corpus import DOCUMENTS, GOLD_QUERIES
from rag_reference.evaluation import compare_retrieval_methods, write_comparison_report
from rag_reference.retrieval import build_chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/retrieval_comparison.json"),
    )
    parser.add_argument("--chunk-size", type=int, default=80)
    parser.add_argument("--overlap", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rrf-k", type=int, default=60)
    args = parser.parse_args()

    chunks = build_chunks(
        DOCUMENTS, chunk_size=args.chunk_size, overlap=args.overlap
    )
    report = compare_retrieval_methods(
        GOLD_QUERIES, chunks, top_k=args.top_k, rrf_k=args.rrf_k
    )
    write_comparison_report(report, args.output)
    for method in report.methods:
        rows = [row for row in report.diagnostics if row.method == method]
        mean_recall = sum(row.recall_at_k for row in rows) / len(rows)
        mean_rr = sum(row.reciprocal_rank for row in rows) / len(rows)
        mean_ndcg = sum(row.ndcg_at_k for row in rows) / len(rows)
        failures = sum(row.failure_class != "passed" for row in rows)
        print(
            f"method={method} queries={len(rows)} recall@{args.top_k}={mean_recall:.3f} "
            f"mrr={mean_rr:.3f} ndcg@{args.top_k}={mean_ndcg:.3f} "
            f"failures={failures} chunks={len(chunks)}"
        )
    print(f"raw ranking evidence: {args.output}")


if __name__ == "__main__":
    main()
