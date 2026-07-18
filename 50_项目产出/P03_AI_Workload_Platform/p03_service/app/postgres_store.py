from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .auth import Principal
from .metrics import TaskMetricsSnapshot
from .models import TaskCreate, TaskRecord, TaskStatus


NON_RETRYABLE_ERRORS = {
    "collection_not_found",
    "forced_failure",
    "invalid_input",
    "invalid_sleep_ms",
    "permission_denied",
    "invalid_rag_input",
}

TASK_COLUMNS = """
    task_id, tenant_id, user_id, allowed_permission_groups, task_type,
    priority, estimated_duration_ms, idempotency_key, input_json, status,
    result_json, error_type, created_at, queued_at, started_at, finished_at,
    runtime_ms, version
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresTaskStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def ping(self) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)

    def submit(self, payload: TaskCreate, principal: Principal) -> tuple[TaskRecord, bool]:
        now = utc_now()
        task_id = str(uuid4())
        with self.connect() as connection:
            with connection.transaction():
                row = connection.execute(
                    f"""
                    INSERT INTO tasks (
                        task_id, tenant_id, user_id, allowed_permission_groups,
                        task_type, priority, estimated_duration_ms,
                        idempotency_key, input_json, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, user_id, idempotency_key) DO NOTHING
                    RETURNING {TASK_COLUMNS}
                    """,
                    (
                        task_id,
                        principal.tenant_id,
                        principal.user_id,
                        list(principal.allowed_permission_groups),
                        payload.task_type,
                        payload.priority,
                        payload.estimated_duration_ms,
                        payload.idempotency_key,
                        Jsonb(payload.input_json),
                        TaskStatus.PENDING.value,
                        now,
                    ),
                ).fetchone()
                if row is None:
                    existing = connection.execute(
                        f"""
                        SELECT {TASK_COLUMNS} FROM tasks
                        WHERE tenant_id = %s AND user_id = %s AND idempotency_key = %s
                        """,
                        (
                            principal.tenant_id,
                            principal.user_id,
                            payload.idempotency_key,
                        ),
                    ).fetchone()
                    if existing is None:
                        raise RuntimeError("idempotent task disappeared after conflict")
                    return self._record(existing), False

                connection.execute(
                    """
                    INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                    VALUES (%s, 'task_submitted', %s, %s)
                    """,
                    (task_id, Jsonb({"task_id": task_id}), now),
                )
                return self._record(row), True

    def get(
        self,
        task_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> TaskRecord | None:
        owner_filter = ""
        params: list[object] = [task_id]
        if tenant_id is not None:
            owner_filter += " AND tenant_id = %s"
            params.append(tenant_id)
        if user_id is not None:
            owner_filter += " AND user_id = %s"
            params.append(user_id)
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {TASK_COLUMNS} FROM tasks WHERE task_id = %s{owner_filter}",
                params,
            ).fetchone()
            return None if row is None else self._record(row)

    def metrics(self, run_id: str | None = None) -> TaskMetricsSnapshot:
        filter_sql = "(%s::text IS NULL OR input_json ->> 'run_id' = %s)"
        filter_params = (run_id, run_id)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT status, COUNT(*) AS count
                FROM tasks
                WHERE {filter_sql}
                GROUP BY status
                """,
                filter_params,
            ).fetchall()
            summary = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS task_count,
                    AVG(EXTRACT(EPOCH FROM (started_at - queued_at)) * 1000)
                        FILTER (WHERE started_at IS NOT NULL AND queued_at IS NOT NULL)
                        AS average_queue_wait_ms,
                    percentile_cont(0.95) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (started_at - queued_at)) * 1000
                    ) FILTER (WHERE started_at IS NOT NULL AND queued_at IS NOT NULL)
                        AS p95_queue_wait_ms,
                    percentile_cont(0.99) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (started_at - queued_at)) * 1000
                    ) FILTER (WHERE started_at IS NOT NULL AND queued_at IS NOT NULL)
                        AS p99_queue_wait_ms,
                    AVG(runtime_ms) AS average_runtime_ms,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY runtime_ms)
                        FILTER (WHERE runtime_ms IS NOT NULL) AS p95_runtime_ms,
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY runtime_ms)
                        FILTER (WHERE runtime_ms IS NOT NULL) AS p99_runtime_ms,
                    SUM(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000)
                        FILTER (WHERE finished_at IS NOT NULL AND started_at IS NOT NULL)
                        AS worker_busy_time_ms,
                    EXTRACT(EPOCH FROM (
                        MAX(finished_at) FILTER (WHERE finished_at IS NOT NULL)
                        - MIN(created_at)
                    )) * 1000 AS observation_window_ms,
                    COUNT(*) FILTER (
                        WHERE finished_at >= CURRENT_TIMESTAMP - INTERVAL '1 minute'
                    ) AS completed_last_minute
                FROM tasks
                WHERE {filter_sql}
                """,
                filter_params,
            ).fetchone()
            outbox = connection.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM outbox
                JOIN tasks ON tasks.task_id = outbox.task_id
                WHERE outbox.published_at IS NULL
                  AND (%s::text IS NULL OR tasks.input_json ->> 'run_id' = %s)
                """,
                filter_params,
            ).fetchone()
        counts = {status: 0 for status in TaskStatus}
        for row in rows:
            counts[TaskStatus(row["status"])] = int(row["count"])
        return TaskMetricsSnapshot(
            task_count=int(summary["task_count"]),
            status_counts=counts,
            average_queue_wait_ms=self._optional_float(summary["average_queue_wait_ms"]),
            p95_queue_wait_ms=self._optional_float(summary["p95_queue_wait_ms"]),
            p99_queue_wait_ms=self._optional_float(summary["p99_queue_wait_ms"]),
            average_runtime_ms=self._optional_float(summary["average_runtime_ms"]),
            p95_runtime_ms=self._optional_float(summary["p95_runtime_ms"]),
            p99_runtime_ms=self._optional_float(summary["p99_runtime_ms"]),
            worker_busy_time_ms=self._optional_float(summary["worker_busy_time_ms"]),
            observation_window_ms=self._optional_float(summary["observation_window_ms"]),
            completed_last_minute=int(summary["completed_last_minute"]),
            pending_outbox_count=int(outbox["count"]),
        )

    def claim_outbox(
        self,
        dispatcher_id: str,
        limit: int,
        claim_seconds: int,
    ) -> list[dict]:
        now = utc_now()
        expired_before = now - timedelta(seconds=claim_seconds)
        with self.connect() as connection:
            with connection.transaction():
                rows = connection.execute(
                    """
                    SELECT event_id, task_id
                    FROM outbox
                    WHERE published_at IS NULL
                      AND (claimed_at IS NULL OR claimed_at <= %s)
                    ORDER BY event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                    """,
                    (expired_before, limit),
                ).fetchall()
                for row in rows:
                    connection.execute(
                        """
                        UPDATE outbox
                        SET claimed_at = %s, claimed_by = %s
                        WHERE event_id = %s AND published_at IS NULL
                        """,
                        (now, dispatcher_id, row["event_id"]),
                    )
                    connection.execute(
                        """
                        UPDATE tasks
                        SET status = %s, queued_at = %s, version = version + 1
                        WHERE task_id = %s AND status IN (%s, %s)
                        """,
                        (
                            TaskStatus.QUEUED.value,
                            now,
                            row["task_id"],
                            TaskStatus.PENDING.value,
                            TaskStatus.RETRYING.value,
                        ),
                    )
                return [dict(row) for row in rows]

    def mark_outbox_published(self, event_id: int, dispatcher_id: str) -> None:
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE outbox
                SET published_at = %s, claimed_at = NULL, claimed_by = NULL
                WHERE event_id = %s AND claimed_by = %s AND published_at IS NULL
                """,
                (utc_now(), event_id, dispatcher_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("outbox publish acknowledgement lost its claim")

    def release_outbox_claim(self, event_id: int, dispatcher_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE outbox
                SET claimed_at = NULL, claimed_by = NULL
                WHERE event_id = %s AND claimed_by = %s AND published_at IS NULL
                """,
                (event_id, dispatcher_id),
            )

    def claim_task(
        self, task_id: str, worker_id: str, lease_seconds: int
    ) -> TaskRecord | None:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                f"""
                UPDATE tasks
                SET status = %s, started_at = %s, worker_id = %s,
                    lease_until = %s, delivery_count = delivery_count + 1,
                    version = version + 1
                WHERE task_id = %s AND status = %s
                RETURNING {TASK_COLUMNS}
                """,
                (
                    TaskStatus.RUNNING.value,
                    now,
                    worker_id,
                    now + timedelta(seconds=lease_seconds),
                    task_id,
                    TaskStatus.QUEUED.value,
                ),
            ).fetchone()
            return None if row is None else self._record(row)

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        lease_seconds: int,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE tasks
                SET lease_until = %s
                WHERE task_id = %s AND worker_id = %s AND status = %s
                  AND version = %s AND lease_until > %s
                """,
                (
                    now + timedelta(seconds=lease_seconds),
                    task_id,
                    worker_id,
                    TaskStatus.RUNNING.value,
                    claim_version,
                    now,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("heartbeat rejected for non-owner or non-running task")

    def succeed(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        result_json: dict,
        runtime_ms: float,
    ) -> TaskRecord:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                f"""
                UPDATE tasks
                SET status = %s, result_json = %s, error_type = NULL,
                    runtime_ms = %s, finished_at = %s,
                    lease_until = NULL, version = version + 1
                WHERE task_id = %s AND worker_id = %s AND status = %s
                  AND version = %s AND lease_until > %s
                RETURNING {TASK_COLUMNS}
                """,
                (
                    TaskStatus.SUCCEEDED.value,
                    Jsonb(result_json),
                    runtime_ms,
                    now,
                    task_id,
                    worker_id,
                    TaskStatus.RUNNING.value,
                    claim_version,
                    now,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("compare-and-set failed while completing task")
            return self._record(row)

    def fail(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        error_type: str,
        runtime_ms: float,
    ) -> TaskStatus:
        now = utc_now()
        with self.connect() as connection:
            with connection.transaction():
                task = connection.execute(
                    """
                    SELECT retry_count, max_retries, status, worker_id,
                           version, lease_until
                    FROM tasks WHERE task_id = %s FOR UPDATE
                    """,
                    (task_id,),
                ).fetchone()
                if (
                    task is None
                    or task["status"] != TaskStatus.RUNNING.value
                    or task["worker_id"] != worker_id
                    or task["version"] != claim_version
                    or task["lease_until"] is None
                    or task["lease_until"] <= now
                ):
                    raise RuntimeError("task is not owned by this claim or its lease expired")

                should_retry = (
                    error_type not in NON_RETRYABLE_ERRORS
                    and task["retry_count"] < task["max_retries"]
                )
                if should_retry:
                    target = TaskStatus.RETRYING
                    connection.execute(
                        """
                        UPDATE tasks
                        SET status = %s, error_type = %s, runtime_ms = %s,
                            retry_count = retry_count + 1, started_at = NULL,
                            worker_id = NULL, lease_until = NULL, version = version + 1
                        WHERE task_id = %s AND version = %s
                        """,
                        (target.value, error_type, runtime_ms, task_id, claim_version),
                    )
                    connection.execute(
                        """
                        INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                        VALUES (%s, 'task_retry_requested', %s, %s)
                        """,
                        (task_id, Jsonb({"task_id": task_id}), now),
                    )
                else:
                    target = TaskStatus.FAILED
                    connection.execute(
                        """
                        UPDATE tasks
                        SET status = %s, error_type = %s, runtime_ms = %s,
                            finished_at = %s, lease_until = NULL,
                            version = version + 1
                        WHERE task_id = %s AND version = %s
                        """,
                        (
                            target.value,
                            error_type,
                            runtime_ms,
                            now,
                            task_id,
                            claim_version,
                        ),
                    )
                return target

    def reconcile_expired_leases(self) -> int:
        now = utc_now()
        with self.connect() as connection:
            with connection.transaction():
                rows = connection.execute(
                    """
                    SELECT task_id, retry_count, max_retries
                    FROM tasks
                    WHERE status = %s AND lease_until IS NOT NULL AND lease_until <= %s
                    ORDER BY lease_until
                    FOR UPDATE SKIP LOCKED
                    """,
                    (TaskStatus.RUNNING.value, now),
                ).fetchall()
                for row in rows:
                    if row["retry_count"] < row["max_retries"]:
                        connection.execute(
                            """
                            UPDATE tasks
                            SET status = %s, error_type = 'worker_lease_expired',
                                retry_count = retry_count + 1, started_at = NULL,
                                worker_id = NULL, lease_until = NULL,
                                version = version + 1
                            WHERE task_id = %s
                            """,
                            (TaskStatus.RETRYING.value, row["task_id"]),
                        )
                        connection.execute(
                            """
                            INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                            VALUES (%s, 'task_lease_recovered', %s, %s)
                            """,
                            (
                                row["task_id"],
                                Jsonb({"task_id": str(row["task_id"])}),
                                now,
                            ),
                        )
                    else:
                        connection.execute(
                            """
                            UPDATE tasks
                            SET status = %s, error_type = 'worker_lease_expired',
                                finished_at = %s, lease_until = NULL,
                                version = version + 1
                            WHERE task_id = %s
                            """,
                            (TaskStatus.FAILED.value, now, row["task_id"]),
                        )
                return len(rows)

    @staticmethod
    def _record(row: dict) -> TaskRecord:
        values = dict(row)
        values["task_id"] = str(values["task_id"])
        return TaskRecord.model_validate(values)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return None if value is None else float(value)
