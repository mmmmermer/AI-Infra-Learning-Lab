from datetime import datetime, timedelta, timezone

import pytest

from e06_reference import RetryPolicy, TaskDatabase, TaskStatus


NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
NO_JITTER_RETRY = RetryPolicy(
    max_attempts=4,
    base_delay_seconds=1,
    max_delay_seconds=8,
    jitter_ratio=0,
)


def test_submit_is_atomic_and_idempotent(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")

    task_id, created = database.submit_task("same-request", {"query": "one"}, now=NOW)
    repeated_id, repeated_created = database.submit_task(
        "same-request", {"query": "changed"}, now=NOW
    )

    assert created is True
    assert repeated_created is False
    assert repeated_id == task_id
    assert database.get_task(task_id)["status"] == TaskStatus.PENDING
    assert database.dispatch_outbox(now=NOW) == 1
    assert database.get_task(task_id)["status"] == TaskStatus.QUEUED


def test_worker_claim_and_complete_use_compare_and_set(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")
    task_id, _ = database.submit_task("request", {"query": "rag"}, now=NOW)
    database.dispatch_outbox(now=NOW)

    claimed = database.claim_next("worker-1", now=NOW)
    assert claimed["task_id"] == task_id
    assert claimed["status"] == TaskStatus.RUNNING

    database.complete_task(
        task_id,
        "worker-1",
        claimed["version"],
        {"answer": "ok"},
        now=NOW + timedelta(seconds=1),
    )
    assert database.get_task(task_id)["status"] == TaskStatus.SUCCEEDED
    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=2)) is None


def test_stale_outbox_cannot_reopen_a_terminal_task(tmp_path):
    database = TaskDatabase(tmp_path / "terminal.db")
    task_id, _ = database.submit_task("terminal", {}, max_retries=0, now=NOW)
    database.dispatch_outbox(now=NOW)
    claimed = database.claim_next("worker-1", now=NOW)
    database.complete_task(
        task_id,
        "worker-1",
        claimed["version"],
        {"answer": "done"},
        now=NOW + timedelta(seconds=1),
    )
    events_before = database.get_events(task_id)

    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO outbox (task_id, event_type, payload_json, created_at)
            VALUES (?, 'task_submitted', '{}', ?)
            """,
            (task_id, NOW.isoformat()),
        )

    with pytest.raises(RuntimeError, match="source does not match"):
        database.dispatch_outbox(now=NOW + timedelta(seconds=2))

    assert database.get_task(task_id)["status"] == TaskStatus.SUCCEEDED
    assert database.get_events(task_id) == events_before
    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM queue_messages WHERE task_id = ?", (task_id,)
        ).fetchone()[0] == 0


def test_deterministic_error_is_not_retried(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")
    task_id, _ = database.submit_task("missing", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    claimed = database.claim_next("worker-1", now=NOW)

    target = database.fail_task(
        task_id,
        "worker-1",
        claimed["version"],
        "collection_not_found",
        now=NOW,
    )

    assert target == TaskStatus.FAILED
    assert database.get_task(task_id)["retry_count"] == 0
    assert database.dispatch_outbox(now=NOW) == 0


def test_retryable_error_requeues_through_outbox(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db", retry_policy=NO_JITTER_RETRY)
    task_id, _ = database.submit_task("timeout", {}, max_retries=2, now=NOW)
    database.dispatch_outbox(now=NOW)
    claimed = database.claim_next("worker-1", now=NOW)

    target = database.fail_task(
        task_id,
        "worker-1",
        claimed["version"],
        "worker_timeout",
        now=NOW,
    )
    assert target == TaskStatus.RETRYING
    assert database.dispatch_outbox(now=NOW + timedelta(seconds=1)) == 1

    claimed_again = database.claim_next("worker-2", now=NOW + timedelta(seconds=1))
    assert claimed_again["task_id"] == task_id
    assert claimed_again["retry_count"] == 1


def test_expired_lease_allows_recovery_after_reconciliation(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db", retry_policy=NO_JITTER_RETRY)
    task_id, _ = database.submit_task("lease", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    database.claim_next("worker-1", lease_seconds=5, now=NOW)

    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=6)) is None
    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=6)) == 1
    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=6)) is None
    recovered = database.claim_next("worker-2", now=NOW + timedelta(seconds=7))
    assert recovered["task_id"] == task_id
    assert recovered["status"] == TaskStatus.RUNNING


def test_heartbeat_extends_lease_and_rejects_wrong_worker(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")
    task_id, _ = database.submit_task("heartbeat", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    database.claim_next("worker-1", lease_seconds=5, now=NOW)

    claimed = database.get_task(task_id)
    database.heartbeat(
        task_id,
        "worker-1",
        claimed["version"],
        lease_seconds=10,
        now=NOW + timedelta(seconds=4),
    )
    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=6)) == 0

    try:
        database.heartbeat(
            task_id,
            "worker-2",
            claimed["version"],
            now=NOW + timedelta(seconds=6),
        )
    except RuntimeError as error:
        assert "heartbeat rejected" in str(error)
    else:
        raise AssertionError("wrong worker heartbeat should fail")


def test_expired_heartbeat_cannot_resurrect_claim(tmp_path):
    database = TaskDatabase(tmp_path / "expired-heartbeat.db")
    task_id, _ = database.submit_task("expired-heartbeat", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    claimed = database.claim_next("worker-1", lease_seconds=5, now=NOW)

    with pytest.raises(RuntimeError, match="heartbeat rejected"):
        database.heartbeat(
            task_id,
            "worker-1",
            claimed["version"],
            lease_seconds=30,
            now=NOW + timedelta(seconds=5),
        )

    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=5)) == 1
    assert database.get_task(task_id)["status"] == TaskStatus.QUEUED


@pytest.mark.parametrize("operation", ["claim", "heartbeat"])
def test_lease_duration_must_be_positive(tmp_path, operation):
    database = TaskDatabase(tmp_path / f"invalid-{operation}.db")
    task_id, _ = database.submit_task(f"invalid-{operation}", {}, now=NOW)
    database.dispatch_outbox(now=NOW)

    if operation == "claim":
        with pytest.raises(ValueError, match="lease_seconds must be positive"):
            database.claim_next("worker-1", lease_seconds=0, now=NOW)
    else:
        claimed = database.claim_next("worker-1", now=NOW)
        with pytest.raises(ValueError, match="lease_seconds must be positive"):
            database.heartbeat(
                task_id,
                "worker-1",
                claimed["version"],
                lease_seconds=0,
                now=NOW,
            )


def test_expired_or_stale_claim_cannot_finalize_reassigned_task(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db", retry_policy=NO_JITTER_RETRY)
    task_id, _ = database.submit_task("stale-owner", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    first_claim = database.claim_next("worker-1", lease_seconds=5, now=NOW)

    try:
        database.complete_task(
            task_id,
            "worker-1",
            first_claim["version"],
            {"answer": "late"},
            now=NOW + timedelta(seconds=6),
        )
    except RuntimeError as error:
        assert "compare-and-set failed" in str(error)
    else:
        raise AssertionError("an expired lease must not finalize")

    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=6)) == 1
    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=6)) is None
    second_claim = database.claim_next(
        "worker-2", lease_seconds=5, now=NOW + timedelta(seconds=7)
    )
    assert second_claim["version"] > first_claim["version"]

    for operation in ("complete", "fail"):
        try:
            if operation == "complete":
                database.complete_task(
                    task_id,
                    "worker-1",
                    first_claim["version"],
                    {"answer": "stale"},
                    now=NOW + timedelta(seconds=8),
                )
            else:
                database.fail_task(
                    task_id,
                    "worker-1",
                    first_claim["version"],
                    "worker_timeout",
                    now=NOW + timedelta(seconds=8),
                )
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"stale worker {operation} should fail")

    database.complete_task(
        task_id,
        "worker-2",
        second_claim["version"],
        {"answer": "current"},
        now=NOW + timedelta(seconds=8),
    )
    assert database.get_task(task_id)["status"] == TaskStatus.SUCCEEDED
