from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from e06_reference import (
    CrashPoint,
    DeliverySemantics,
    RetryPolicy,
    TaskDatabase,
    TaskStatus,
    build_retry_schedule,
    derive_crash_outcome,
    peak_retry_load,
    retry_delay_seconds,
)


NOW = datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)
NO_JITTER_RETRY = RetryPolicy(
    max_attempts=4,
    base_delay_seconds=1,
    max_delay_seconds=8,
    jitter_ratio=0,
)


@pytest.mark.parametrize(
    ("semantics", "crash_point", "effects", "lost", "duplicate"),
    [
        (
            DeliverySemantics.AT_MOST_ONCE,
            CrashPoint.AFTER_RECEIVE_BEFORE_EFFECT,
            0,
            True,
            False,
        ),
        (
            DeliverySemantics.AT_LEAST_ONCE,
            CrashPoint.AFTER_EFFECT_BEFORE_FINALIZE,
            2,
            False,
            True,
        ),
        (
            DeliverySemantics.EFFECTIVELY_ONCE,
            CrashPoint.AFTER_EFFECT_BEFORE_FINALIZE,
            1,
            False,
            False,
        ),
        (
            DeliverySemantics.EFFECTIVELY_ONCE,
            CrashPoint.AFTER_FINALIZE_BEFORE_ACK,
            1,
            False,
            False,
        ),
    ],
)
def test_delivery_semantics_are_derived_from_crash_point(
    semantics, crash_point, effects, lost, duplicate
):
    outcome = derive_crash_outcome(semantics, crash_point)
    assert outcome.effect_count == effects
    assert outcome.lost_or_inconsistent is lost
    assert outcome.duplicate_effect is duplicate


def test_retry_policy_is_bounded_deterministic_and_capped():
    policy = RetryPolicy(
        max_attempts=4,
        base_delay_seconds=1,
        max_delay_seconds=5,
        jitter_ratio=0.4,
    )

    first = [retry_delay_seconds("task-7", n, policy) for n in range(1, 5)]
    second = [retry_delay_seconds("task-7", n, policy) for n in range(1, 5)]

    assert first == second
    assert all(0 < delay <= policy.max_delay_seconds for delay in first)
    with pytest.raises(ValueError, match="bounded retry policy"):
        retry_delay_seconds("task-7", 5, policy)


def test_deterministic_jitter_reduces_retry_storm_peak():
    task_keys = [f"task-{number:03d}" for number in range(200)]
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=1,
        max_delay_seconds=8,
        jitter_ratio=0.5,
    )

    synchronized = build_retry_schedule(task_keys, policy, jitter=False)
    dispersed = build_retry_schedule(task_keys, policy, jitter=True)

    assert peak_retry_load(synchronized) == len(task_keys)
    assert peak_retry_load(dispersed) < len(task_keys) // 2


def test_transition_events_are_ordered_complete_and_immutable(tmp_path):
    database = TaskDatabase(tmp_path / "events.db", retry_policy=NO_JITTER_RETRY)
    task_id, _ = database.submit_task("event-sequence", {}, max_retries=1, now=NOW)
    database.dispatch_outbox(now=NOW)
    first = database.claim_next("worker-1", now=NOW)
    assert (
        database.fail_task(
            task_id,
            "worker-1",
            first["version"],
            "worker_timeout",
            now=NOW + timedelta(seconds=1),
        )
        == TaskStatus.RETRYING
    )
    database.dispatch_outbox(now=NOW + timedelta(seconds=2))
    second = database.claim_next("worker-2", now=NOW + timedelta(seconds=2))
    database.complete_task(
        task_id,
        "worker-2",
        second["version"],
        {"answer": "ok"},
        now=NOW + timedelta(seconds=3),
    )

    events = database.get_events(task_id)
    assert [event["to_status"] for event in events] == [
        TaskStatus.PENDING,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.RETRYING,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.SUCCEEDED,
    ]
    assert [event["task_version"] for event in events] == list(range(7))
    assert [event["retry_count"] for event in events] == [0, 0, 0, 1, 1, 1, 1]

    with database.connection() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE task_events SET event_type = 'forged' WHERE task_id = ?",
                (task_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))


def test_stale_owner_failure_cannot_forge_an_event(tmp_path):
    database = TaskDatabase(
        tmp_path / "stale-event.db", retry_policy=NO_JITTER_RETRY
    )
    task_id, _ = database.submit_task("stale-event", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    stale = database.claim_next("worker-old", lease_seconds=1, now=NOW)
    database.reconcile_expired_leases(now=NOW + timedelta(seconds=2))
    current = database.claim_next(
        "worker-current", lease_seconds=10, now=NOW + timedelta(seconds=3)
    )
    before = database.get_events(task_id)

    with pytest.raises(RuntimeError, match="not owned"):
        database.fail_task(
            task_id,
            "worker-old",
            stale["version"],
            "worker_timeout",
            now=NOW + timedelta(seconds=3),
        )

    assert database.get_events(task_id) == before
    database.complete_task(
        task_id,
        "worker-current",
        current["version"],
        {"answer": "current owner"},
        now=NOW + timedelta(seconds=3),
    )


def test_retry_budget_ends_in_failed_without_an_extra_outbox_event(tmp_path):
    database = TaskDatabase(
        tmp_path / "retry-budget.db", retry_policy=NO_JITTER_RETRY
    )
    task_id, _ = database.submit_task("retry-budget", {}, max_retries=1, now=NOW)
    database.dispatch_outbox(now=NOW)
    first = database.claim_next("worker-1", now=NOW)
    database.fail_task(
        task_id,
        "worker-1",
        first["version"],
        "worker_timeout",
        now=NOW,
    )
    assert database.dispatch_outbox(now=NOW + timedelta(seconds=1)) == 1
    second = database.claim_next("worker-2", now=NOW + timedelta(seconds=1))

    assert (
        database.fail_task(
            task_id,
            "worker-2",
            second["version"],
            "worker_timeout",
            now=NOW + timedelta(seconds=2),
        )
        == TaskStatus.FAILED
    )
    task = database.get_task(task_id)
    assert task["retry_count"] == 1
    assert task["last_error"] == "worker_timeout"
    assert database.dispatch_outbox(now=NOW + timedelta(seconds=3)) == 0
    assert database.get_events(task_id)[-1]["to_status"] == TaskStatus.FAILED


def test_repeated_worker_crashes_consume_recovery_budget(tmp_path):
    database = TaskDatabase(
        tmp_path / "lease-budget.db", retry_policy=NO_JITTER_RETRY
    )
    task_id, _ = database.submit_task("lease-budget", {}, max_retries=1, now=NOW)
    database.dispatch_outbox(now=NOW)
    database.claim_next("worker-1", lease_seconds=1, now=NOW)

    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=2)) == 1
    after_first_crash = database.get_task(task_id)
    assert after_first_crash["status"] == TaskStatus.QUEUED
    assert after_first_crash["retry_count"] == 1

    assert database.claim_next("worker-2", now=NOW + timedelta(seconds=2)) is None
    database.claim_next(
        "worker-2", lease_seconds=1, now=NOW + timedelta(seconds=3)
    )
    assert database.reconcile_expired_leases(now=NOW + timedelta(seconds=4)) == 1

    exhausted = database.get_task(task_id)
    assert exhausted["status"] == TaskStatus.FAILED
    assert exhausted["retry_count"] == 1
    assert exhausted["error_type"] == "lease_expired"
    assert database.claim_next("worker-3", now=NOW + timedelta(seconds=5)) is None
    assert database.get_events(task_id)[-1]["event_type"] == "lease_recovery_exhausted"


def test_task_database_retry_uses_injected_exponential_backoff_and_jitter(tmp_path):
    policy = RetryPolicy(
        max_attempts=2,
        base_delay_seconds=4,
        max_delay_seconds=30,
        jitter_ratio=0.2,
    )
    database = TaskDatabase(tmp_path / "scheduled-retry.db", retry_policy=policy)
    task_id, _ = database.submit_task(
        "scheduled-retry", {}, max_retries=2, now=NOW
    )
    database.dispatch_outbox(now=NOW)
    first = database.claim_next("worker-1", now=NOW)

    database.fail_task(
        task_id,
        "worker-1",
        first["version"],
        "worker_timeout",
        now=NOW,
    )
    database.dispatch_outbox(now=NOW)
    first_delay = retry_delay_seconds(task_id, 1, policy)
    first_due = NOW + timedelta(seconds=first_delay)
    assert database.claim_next(
        "too-early-1", now=first_due - timedelta(microseconds=1)
    ) is None
    second = database.claim_next("worker-2", now=first_due)
    assert second["retry_count"] == 1

    database.fail_task(
        task_id,
        "worker-2",
        second["version"],
        "worker_timeout",
        now=first_due,
    )
    database.dispatch_outbox(now=first_due)
    second_delay = retry_delay_seconds(task_id, 2, policy)
    second_due = first_due + timedelta(seconds=second_delay)
    assert second_delay > first_delay
    assert database.claim_next(
        "too-early-2", now=second_due - timedelta(microseconds=1)
    ) is None
    third = database.claim_next("worker-3", now=second_due)
    assert third["retry_count"] == 2


def test_fail_task_executes_owner_lease_and_version_fencing_in_one_update(tmp_path):
    database = TaskDatabase(tmp_path / "atomic-fail.db", retry_policy=NO_JITTER_RETRY)
    task_id, _ = database.submit_task("atomic-fail", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    claim = database.claim_next("worker-1", lease_seconds=10, now=NOW)
    statements: list[str] = []
    original_connect = database.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    database.connect = traced_connect
    assert database.fail_task(
        task_id,
        "worker-1",
        claim["version"],
        "worker_timeout",
        now=NOW + timedelta(seconds=1),
    ) == TaskStatus.RETRYING

    task_updates = [
        " ".join(statement.upper().split())
        for statement in statements
        if statement.lstrip().upper().startswith("UPDATE TASKS")
    ]
    assert len(task_updates) == 1
    update = task_updates[0]
    assert "TASK_ID =" in update and "STATUS =" in update and "VERSION =" in update
    assert "QUEUE_MESSAGES.WORKER_ID =" in update
    assert "QUEUE_MESSAGES.LEASED_UNTIL >" in update
