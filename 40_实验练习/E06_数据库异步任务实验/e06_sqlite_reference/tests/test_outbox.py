from datetime import datetime, timedelta, timezone

from e06_reference import TaskDatabase, TaskStatus


NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


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
    database = TaskDatabase(tmp_path / "tasks.db")
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
    database = TaskDatabase(tmp_path / "tasks.db")
    task_id, _ = database.submit_task("lease", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    database.claim_next("worker-1", lease_seconds=5, now=NOW)

    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=6)) is None
    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=6)) == 1
    recovered = database.claim_next("worker-2", now=NOW + timedelta(seconds=6))
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


def test_expired_or_stale_claim_cannot_finalize_reassigned_task(tmp_path):
    database = TaskDatabase(tmp_path / "tasks.db")
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
    second_claim = database.claim_next(
        "worker-2", lease_seconds=5, now=NOW + timedelta(seconds=6)
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
                    now=NOW + timedelta(seconds=7),
                )
            else:
                database.fail_task(
                    task_id,
                    "worker-1",
                    first_claim["version"],
                    "worker_timeout",
                    now=NOW + timedelta(seconds=7),
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
        now=NOW + timedelta(seconds=7),
    )
    assert database.get_task(task_id)["status"] == TaskStatus.SUCCEEDED
