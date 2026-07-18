# P03 Workload Platform v0.3.1

Executable reference implementation with two explicit modes:

- `memory`: one-process teaching mode used by unit tests.
- `postgres`: five-service Compose mode with PostgreSQL, Redis, API,
  transactional-outbox dispatcher, and an independent worker.

The worker supports both deterministic mock workloads and an E03-derived BM25
retrieval workload. The retrieval path uses a fixed corpus, tenant filtering,
permission prefiltering, and persistent source metadata. It does not claim LLM
generation, vector-database, Agent, or model-serving quality.

## Reference Authentication

Task endpoints require a bearer token. The development-only registry is
server-owned; task payloads cannot provide or override tenant, user, or
permission groups.

| Token | Tenant/user | Permission groups | Operator |
|---|---|---|---|
| `reference-public-token` | reference/public | public | no |
| `reference-compliance-token` | reference/compliance | public, compliance_private | no |
| `reference-empty-token` | empty/empty | public | no |
| `reference-other-token` | other/other | public | no |
| `reference-ops-token` | reference/ops | public | yes |

Example header:

```text
Authorization: Bearer reference-public-token
```

These tokens are test fixtures, not production credentials. A deployed system
must replace this registry with authenticated identity verification and a
server-side permission lookup.

## Memory Mode

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python -m uvicorn app.main:app --reload
```

Memory mode keeps the manual `POST /workers/run-next` endpoint so the state
machine can be tested without Docker. Process restart intentionally loses data.

## Fixed Replay Sender

The reference sender replays a CSV arrival schedule without waiting for the
previous response. It validates each JSON payload with the current `TaskCreate`
schema, injects a unique `run_id:request_id` idempotency key, and optionally
polls each owner-scoped task to a terminal state.

```powershell
$env:P03_REPLAY_BEARER_TOKEN = '<development-bearer-token>'
python -m app.fixed_replay `
  .\load\fixed_replay_example\manifest.csv `
  .\artifacts\fixed_replay_results.csv `
  --base-url http://127.0.0.1:8001 `
  --run-id fixed-replay-001 `
  --poll-timeout-seconds 60
```

The bearer token is read only from the environment. The output records planned
and actual start times, start lateness, API response latency, task id, optional
terminal completion time, and errors. Sender unit tests prove scheduling and
export semantics; they are not a service benchmark or capacity result.

## Compose Mode

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/ready
.\scripts\verify_compose.ps1
```

Run the isolated worker-scaling reference smoke:

```powershell
.\scripts\run_worker_scaling_smoke.ps1 `
  -WorkerCounts 1,2,4 `
  -Users 5 `
  -RunTime 10s `
  -RequestsPerUser 5
```

Run the randomized repeated local reference with queue and worker-resource
time series plus 95% Student t intervals:

```powershell
.\scripts\run_worker_scaling_repeated.ps1 `
  -WorkerCounts 1,2,4 `
  -Repeats 3 `
  -Users 5 `
  -RunTime 5s `
  -RandomSeed 20260711
```

Clean up the reference data after verification:

```powershell
docker compose down -v --remove-orphans
```

Do not add `-v` when you intend to keep the PostgreSQL and Redis named volumes.
The v0.3 schema introduced owner and permission columns; recreate pre-v0.3 local
teaching volumes before upgrading to the current v0.3.1 reference. A production upgrade would require
an explicit database migration rather than volume deletion.

## Distributed Flow

```text
POST /tasks
-> one PostgreSQL transaction inserts task(status=pending) and outbox event
-> dispatcher leases the outbox event and changes task to queued
-> dispatcher XADDs only task_id to a Redis Stream
-> independent worker reserves it through XREADGROUP
-> PostgreSQL CAS changes queued -> running and returns a claim version
-> mock or permission-prefiltered RAG retrieval workload executes
-> owner/version/lease-checked CAS changes running -> succeeded/failed
-> worker XACKs and deletes the stream entry only after database finalization
```

Redis delivery is deliberately at least once. If the dispatcher publishes and
then fails before acknowledging the outbox row, the same `task_id` may appear
again. A reserved message remains in the consumer group's pending entries list
until database finalization succeeds and the worker acknowledges it. If a worker
crashes between reserve and database claim, another consumer can reclaim the
idle pending message. A duplicate delivery cannot execute a terminal or
already-running task because `claim_task()` only updates `queued` rows.

An interrupted worker leaves a lease on the running task. After the lease
expires, reconciliation changes the task to `retrying`, writes a new outbox
event in the same transaction, and lets the normal dispatcher path requeue it.
Each claim increments `version`; heartbeat and finalization match worker,
claim version and an unexpired lease, so a stale worker cannot commit after
reassignment.

## HTTP Surface

- `POST /tasks`: authenticated, owner-scoped idempotent task submission.
- `GET /tasks/{task_id}`: owner-scoped persistent task query.
- `GET /metrics`: operator-only status counts, broker/outbox backlog, rolling completions,
  and queue-wait/runtime average, P95, and P99.
- `GET /health`: process liveness only.
- `GET /ready`: PostgreSQL and Redis readiness in Compose mode.
- `POST /workers/run-next`: operator-only memory mode endpoint returning only
  task id, status, and error type; Compose uses the worker service.

`rag_retrieval` accepts `query` and optional `top_k=1..5` in `input_json`.
Security fields in `input_json` are rejected. The worker retrieves only chunks
matching the task's persisted tenant and permission snapshot, then stores an
extractive answer, retrieval timing, security context, and source metadata.

## Verified Behavior

Reference verification was extended on 2026-07-18. The current suite covers:

- 27 tests on Python 3.13, including the fixed golden-query set and three
  fixed-replay sender tests.
- image build and non-root `appuser` execution.
- healthy PostgreSQL, Redis, API, dispatcher, and worker containers.
- idempotent submission and automatic success/failure completion.
- outbox backlog recovery while the dispatcher is stopped.
- worker interruption followed by lease expiry and successful retry.
- API restart with task persistence.
- duplicate Redis Stream delivery rejected without a second execution.
- pending stream delivery reclaimed after a consumer interruption.
- stale claim version or expired lease rejected during finalization.
- missing/invalid authentication and operator authorization fail closed.
- idempotency and task reads are scoped by tenant and user.
- public RAG retrieval cannot see the private compliance document and returns
  an explicit no-relevant-source result instead of unrelated evidence.
- authorized compliance retrieval returns and persists the private source.
- cross-tenant retrieval is excluded before BM25 ranking.
- an authorized tenant with no corpus receives an explicit empty result.
- run-id-isolated 1/2/4 worker Locust smokes with request/task count checks,
  exported API/task metrics, and task-processing utilization.
- randomized 1/2/4 worker x 3 local runs with 500 ms queue time series,
  worker-container CPU/memory samples, and 95% Student t intervals.
- an 18-task `rag_retrieval` load smoke with zero HTTP/task failures and all
  results persisting `retrieval_status=ok` plus non-empty sources.
- a disposable kind v0.32.0 / Kubernetes v1.34.8 deployment with PostgreSQL,
  Redis, API, dispatcher, and worker Deployments; non-root UID 10001; public
  and compliance RAG permission paths; API rollout persistence; and functional
  scaling to 1/2/4 worker replicas with 24 successful tasks per group.

The verification script creates four tasks and checks database counters for the
lease and duplicate-delivery cases. It is an executable reference check, not a
learner completion record.

## Current Boundary

Implemented:

- PostgreSQL as the task source of truth.
- task and outbox insert in one transaction.
- leased outbox claims with recovery after dispatcher interruption.
- Redis task-id queue with at-least-once delivery.
- idempotency keys and owner-checked state transitions.
- independent worker, deterministic failure path, and expired-lease recovery.
- server-resolved reference principals and owner-scoped task access.
- fixed-corpus BM25 retrieval with tenant and permission prefiltering.
- persistent retrieval answer, timing, source text, and source metadata.
- queue/outbox/task time series and worker-container resource sampling.
- randomized repeated worker-scaling runner and confidence-interval export.
- pinned Python/dependency/image versions, health checks, and named volumes.

Not implemented:

- LLM generation, embeddings, vector database, Agent, or inference service.
- document upload, corpus lifecycle, permission administration, or token rotation.
- production authentication, authorization, secrets management, or TLS.
- idempotency for external side effects performed inside a real workload.
- continuous heartbeat for workloads longer than the five-second mock limit.
- Prometheus histograms, tracing, host/process profiler integration, or dashboards.
- long-duration steady state, warm-up exclusion, raw task export, multi-host runs,
  repeated RAG/LLM load, or capacity conclusions.
- Kubernetes autoscaling or production operations guidance; the separate
  `40_实验练习/E09_K8s实验/kind_reference/` path is a disposable functional
  reference using `emptyDir`, development credentials, and manual scaling.

The local Compose credentials are intentionally development-only and must not be
copied into a deployed environment.
