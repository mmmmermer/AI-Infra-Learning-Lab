# E06 SQLite Reference

Executable teaching reference for:

- atomic task + outbox creation
- idempotent submission
- outbox dispatch
- FIFO queue messages
- compare-and-set state transitions
- retryable vs deterministic errors
- lease, heartbeat, expiry reconciliation and worker recovery
- owner + claim-version fencing for heartbeat and finalization

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

The recovery tests prove that lease expiry alone is insufficient while the task remains `running`; reconciliation must move it back to `queued` before another worker claims it. Every heartbeat, success and failure also carries the `worker_id` and the claim's task `version`. An expired lease or an older claim version cannot finalize a task after reassignment. PostgreSQL/Redis implementations remain a separate reference and must preserve the same fencing rule.
