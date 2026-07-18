# E08 Worker-Scaling Reference Smoke

## Scope

This is one controlled local reference run per worker count. It verifies the
load and metric pipeline; it is not a benchmark, capacity claim, or research
result.

- date: 2026-07-10
- host: local Windows + Docker Desktop
- P03 mode: PostgreSQL/Redis Compose
- API/dispatcher replicas: 1/1
- worker replicas: 1, 2, 4
- workload: deterministic `mock_rag`, `sleep_ms=25`
- Locust: 2.45.0
- users: 5
- spawn rate: 5 users/s
- pacing: `constant_throughput(5)` per user, target about 25 submissions/s
- configured run time: 10 s
- starting task store: empty for every group
- run isolation: unique `run_id` and `GET /metrics?run_id=...`

Locust final JSON request counts were required to equal PostgreSQL task counts.
Each group used new Compose volumes and was drained before metrics were saved.

## Observed Results

| workers | tasks | HTTP failures | API req/s | API P95 | API P99 | queue P95 | queue P99 | task-processing utilization |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 195 | 0 | 25.40 | 70 ms | 72 ms | 6598.49 ms | 6976.23 ms | 0.841 |
| 2 | 195 | 0 | 23.16 | 86 ms | 800 ms | 463.04 ms | 509.03 ms | 0.814 |
| 4 | 190 | 0 | 25.46 | 82 ms | 100 ms | 198.22 ms | 278.32 ms | 0.403 |

Task-processing utilization is:

```text
sum(finished_at - started_at)
-----------------------------------------------
worker_count * (max(finished_at) - min(created_at))
```

It measures the fraction of available worker wall time occupied by a claimed
task. It is not CPU utilization and does not include idle polling before claim.

## Interpretation Boundary

In these three runs, adding workers coincided with much lower queue-wait P95/P99,
while four workers had substantially lower task-processing utilization. This is
the expected latency/resource tradeoff, but one run per group cannot establish
a stable effect. The two-worker API P99 outlier also shows that local jitter is
material.

The later `e08_reference_repeated/` artifact adds three repeats, randomized
group order, confidence intervals, queue-length time series, and worker-container
CPU/memory samples. A formal E08/RQ01 experiment still needs warm-up policy,
long-duration steady state, raw task export, repeated RAG/LLM load, and stronger host
isolation.

## Files

- `worker_scaling_summary.csv`: cross-group summary.
- `workers_N/locust_final.json`: final request counts and response histogram.
- `workers_N/locust_stats.csv`: Locust aggregate export.
- `workers_N/locust_stats_history.csv`: time-series Locust samples.
- `workers_N/metrics_after_drain.json`: run-filtered task metrics.
- `workers_N/run_summary.json`: parameters, utilization, and metrics together.
- `workers_N/locust_failures.csv`: header only for these runs.
- `workers_N/locust_exceptions.csv`: header only for these runs.
