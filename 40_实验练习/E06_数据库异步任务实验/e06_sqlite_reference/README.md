# E06 SQLite Reference

This executable teaching reference isolates database and worker-recovery semantics before the learner adds HTTP, PostgreSQL or Redis.

## What It Proves

- atomic task + outbox creation and idempotent submission
- a versioned schema migration from the original unversioned reference
- database `CHECK`, JSON, foreign-key and uniqueness constraints
- an indexed FIFO claim query with inspectable `EXPLAIN QUERY PLAN` output
- bounded SQLite writer-lock failure and recovery
- compare-and-set transitions whose failure update atomically checks state, version, owner and lease
- terminal-state rejection of stale or mismatched outbox events
- bounded task and lease-recovery retries scheduled by deterministic exponential backoff and jitter
- crash-point comparison for at-most-once, at-least-once and effectively-once processing
- an ordered, queryable `task_events` history protected against update/delete
- stale-owner rejection without forged success or failure events
- deterministic SQLite connection closure, including immediate database-file deletion on Windows

## Run

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

Expected result: `29 passed`.

Inspect the claim plan directly:

```powershell
python -c "from pathlib import Path; from e06_reference import TaskDatabase; print(*TaskDatabase(Path('plan.db')).explain_claim_plan(), sep='\n')"
```

At least one plan step must name `idx_queue_claim`. The test verifies an explicit SQLite access path; it is not evidence that the same index is optimal for PostgreSQL or production traffic.

## Recovery Contract

The task row is the current fact; `task_events` is its append-only transition history within the reference API. Every successful state transition increments `tasks.version` and appends exactly one event with the resulting version in the same transaction. Schema triggers reject event updates and deletes, but they are not a defense against a database administrator who can alter data or drop triggers. Heartbeats do not change task state and therefore do not append transition events. A heartbeat atomically checks owner, claim version, running state and an unexpired existing lease; it cannot resurrect an expired claim. A stale owner, expired lease or old claim version can change neither the task nor its history through the reference methods.

Lease expiry alone is insufficient while the task remains `running`. Reconciliation consumes one retry, moves the task back to `queued`, clears the old owner and advances `available_at` through the injected retry policy before another worker may claim it. When the recovery budget is exhausted, it moves the task to `failed` and removes the queue message. Retryable failure moves `running -> retrying`, calculates the due time, and appends that due time to a retry outbox event in the same transaction. Dispatch preserves the due time when it moves `retrying -> queued`. Both paths use the same `max_retries` budget.

`task_submitted` may dispatch only from `pending`; `task_retry_requested` may dispatch only from `retrying`. A stale event against a terminal task fails closed and cannot create a queue message or append a forged transition.

## Connection Ownership

`TaskDatabase.connection()` is the transaction-scoped API used by the reference. It commits or rolls back and then closes the SQLite connection in a `finally` block. `TaskDatabase.connect()` is the low-level API used only when an experiment must deliberately hold a lock; its caller owns `close()`.

The normal suite includes a Windows-sensitive regression that performs representative database operations and then deletes the database file immediately. The development-mode command below additionally turns unclosed SQLite connections into a test failure:

```powershell
python -X dev -W error::ResourceWarning -m pytest -q
```

## PostgreSQL Deadlock Demo

`examples/postgres_deadlock_demo.py` is an external integration demo, not part of the SQLite test count. It starts two PostgreSQL transactions, locks two rows in opposite order, requires exactly one `40P01` victim, and verifies that the victim's first update was rolled back before dropping its isolated table.

Run it only against a disposable PostgreSQL database:

```powershell
python -m pip install -r requirements-postgres.lock
$env:E06_POSTGRES_DSN = "postgresql://user:password@localhost:5432/e06_lab"
python examples/postgres_deadlock_demo.py
```

Expected final line: `verified: one victim rolled back and one transaction committed`. The presence or syntax check of this script is not PostgreSQL evidence; retain its command output from a real server before marking the deadlock artifact verified.

A successful local reference run against an isolated PostgreSQL 17.9 cluster is recorded in `artifacts/postgres_deadlock_reference_2026-07-18.json`. The cluster used loopback, a non-default port and temporary trust authentication; it was stopped and deleted after verification. This record proves the scripted `40P01`, victim rollback and survivor commit once in that isolated environment. It is not continuous integration evidence and does not represent production concurrency, permissions, topology or load.

## Deliberate Boundaries

- SQLite serializes writers; the default 29-test suite is not a PostgreSQL deadlock reproduction.
- `INDEXED BY` and `EXPLAIN QUERY PLAN` are SQLite-specific teaching aids.
- effectively-once means at-least-once delivery plus an idempotent or transactionally deduplicated effect. The queue itself does not provide exactly-once execution.
- the deterministic failure and retry-storm models are controlled labs, not latency or capacity benchmarks.
- stale or malformed unpublished outbox rows fail the whole dispatch transaction closed. This preserves terminal-state safety but can block later valid rows until an operator repairs or quarantines the poison event; a production dispatcher needs an explicit quarantine/dead-letter policy and alerting.
- PostgreSQL isolation, deadlock victim selection, Redis Streams pending-entry recovery and external side-effect idempotency require their own integration tests.
