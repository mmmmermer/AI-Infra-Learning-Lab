# E08 Repeated Worker-Scaling Reference

Status: `verified local reference / learner pending / not a capacity benchmark`.

Generated on 2026-07-11 with:

- worker counts: 1, 2, 4.
- repeats per worker count: 3.
- randomized execution order with seed `20260711`.
- 5 users, 5 requested submissions/second/user, 5-second Locust window.
- deterministic `mock_rag` workload with `sleep_ms=25`.
- queue/outbox/task sampling every 500 ms.
- worker-container CPU and memory sampling every 1000 ms.
- fresh PostgreSQL and Redis volumes for every run.
- two-sided 95% Student t intervals across the three local runs.

## Selected Results

| Workers | Runs | HTTP failures | Queue P95 mean [95% CI] | Queue P99 mean [95% CI] | Peak broker queue mean [95% CI] | Task-processing utilization mean [95% CI] |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 0 | 2673.41 [1940.58, 3406.25] ms | 2820.45 [2054.82, 3586.09] ms | 34.67 [22.16, 47.17] | 0.825 [0.788, 0.862] |
| 2 | 3 | 0 | 398.44 [124.14, 672.75] ms | 436.33 [185.45, 687.20] ms | 7.33 [2.16, 12.50] | 0.722 [0.580, 0.864] |
| 4 | 3 | 0 | 225.58 [112.03, 339.14] ms | 271.76 [133.21, 410.30] ms | 0.00 [0.00, 0.00] | 0.441 [0.412, 0.470] |

Within this exact local setup, additional workers reduced queue wait and broker
backlog while lowering per-capacity task-processing utilization. The intervals
remain wide at three repeats, especially for the two-worker group. These data
do not establish a production capacity limit or a general scaling law.

## Artifacts

- `randomized_run_plan.csv`: execution order and group assignment.
- `repeated_run_results.csv`: one row per completed run.
- `worker_scaling_confidence_intervals.csv`: long-form mean, sample standard
  deviation, and 95% t interval for each metric.
- `experiment_metadata.json`: fixed protocol and reference boundary.
- `order_*/`: per-run Locust CSV/JSON, queue time series, worker resource time
  series, drained task metrics, and logs.

## Limitations

- The workload is deterministic `mock_rag`, not BM25 retrieval or LLM generation.
- Three repeats are the minimum for a local uncertainty estimate, not a strong
  statistical basis for operational decisions.
- Runs share one Windows/Docker Desktop host and were not isolated from host noise.
- Container CPU is sampled by Docker and summed across worker containers; it is
  not normalized host CPU utilization.
- Request counts varied from 60 to 75 because a fixed-time constant-throughput
  load was used. Every run still passed the Locust request count = database task
  count check.
- No warm-up exclusion, long-duration steady state, multi-host execution, or
  production telemetry backend is included.
