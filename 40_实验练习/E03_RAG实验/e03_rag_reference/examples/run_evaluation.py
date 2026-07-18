from rag_reference.corpus import DOCUMENTS, GOLD_QUERIES
from rag_reference.retrieval import build_chunks, evaluate_queries


def main() -> None:
    for chunk_size, overlap in [(40, 0), (80, 10), (120, 20)]:
        chunks = build_chunks(DOCUMENTS, chunk_size=chunk_size, overlap=overlap)
        rows = evaluate_queries(GOLD_QUERIES, chunks, top_k=3)
        mean_recall = sum(row.recall_at_k for row in rows) / len(rows)
        mean_rr = sum(row.reciprocal_rank for row in rows) / len(rows)
        elapsed_ms = sum(row.retrieval_ms for row in rows)
        print(
            f"chunk_size={chunk_size} overlap={overlap} chunks={len(chunks)} "
            f"recall@3={mean_recall:.3f} mrr={mean_rr:.3f} retrieval_ms={elapsed_ms:.3f}"
        )


if __name__ == "__main__":
    main()
