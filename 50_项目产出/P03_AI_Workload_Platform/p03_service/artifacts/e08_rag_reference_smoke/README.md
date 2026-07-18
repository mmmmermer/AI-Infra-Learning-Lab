# E08 BM25 RAG Retrieval Smoke

Status: `verified single local reference / not a capacity benchmark`.

This run verifies that the E08 load and time-series pipeline can execute the
actual P03 `rag_retrieval` workload rather than only `mock_rag`.

Protocol:

- date: 2026-07-11.
- one API, dispatcher, and worker with fresh PostgreSQL/Redis volumes.
- 3 Locust users, 3 requested submissions/second/user, 4-second window.
- task type: `rag_retrieval`, `top_k=3`.
- fixed public query: `RAG 回答为什么需要来源引用？`.
- queue sampling: 500 ms; worker-container resources: 1000 ms.

Observed:

| tasks | HTTP failures | task failures | retrieval status ok | sources persisted | queue P95 | queue P99 | runtime P95 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 18 | 0 | 0 | 18 | 18 | 139.04 ms | 162.31 ms | 2.17 ms |

The database check required all 18 tasks to persist
`kind=rag_retrieval_reference`, `retrieval_status=ok`, and at least one source.
This is one tiny fixed-corpus run. It does not compare worker counts, embedding
systems, vector databases, LLM generation, or production RAG capacity.

Per-run raw files are in `bm25_single_worker/`.
