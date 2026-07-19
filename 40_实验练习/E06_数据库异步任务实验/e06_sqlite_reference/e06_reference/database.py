from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .reliability import RetryPolicy, retry_delay_seconds


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


SCHEMA_VERSION = 2
NON_RETRYABLE_ERRORS = {"collection_not_found", "invalid_input", "permission_denied"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'reference-tenant',
    user_id TEXT NOT NULL DEFAULT 'reference-user',
    allowed_permission_groups_json TEXT NOT NULL DEFAULT '["public"]'
        CHECK (json_valid(allowed_permission_groups_json)),
    acl_version TEXT NOT NULL DEFAULT 'reference-acl-v1',
    task_type TEXT NOT NULL DEFAULT 'reference_task',
    priority INTEGER NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    estimated_duration_ms INTEGER NOT NULL DEFAULT 0
        CHECK (estimated_duration_ms >= 0),
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')
    ),
    input_json TEXT NOT NULL CHECK (json_valid(input_json)),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_type TEXT,
    last_error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries BETWEEN 0 AND 100),
    created_at TEXT NOT NULL,
    queued_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    CHECK (retry_count <= max_retries),
    UNIQUE (tenant_id, user_id, idempotency_key),
    CHECK (
        status NOT IN ('succeeded', 'failed', 'cancelled') OR finished_at IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS outbox (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('task_submitted', 'task_retry_requested')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    published_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS queue_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL UNIQUE,
    available_at TEXT NOT NULL,
    leased_until TEXT,
    worker_id TEXT,
    delivery_count INTEGER NOT NULL DEFAULT 0 CHECK (delivery_count >= 0),
    CHECK (
        (leased_until IS NULL AND worker_id IS NULL)
        OR (leased_until IS NOT NULL AND worker_id IS NOT NULL)
    ),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT CHECK (
        from_status IS NULL OR from_status IN (
            'pending', 'queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled'
        )
    ),
    to_status TEXT NOT NULL CHECK (
        to_status IN ('pending', 'queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')
    ),
    task_version INTEGER NOT NULL CHECK (task_version >= 0),
    worker_id TEXT,
    retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(task_id, task_version),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox(event_id) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_queue_claim
    ON queue_messages(available_at, leased_until, message_id, task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_history
    ON task_events(task_id, task_version, event_id);
CREATE INDEX IF NOT EXISTS idx_tasks_owner_lookup
    ON tasks(tenant_id, user_id, task_id);

CREATE TRIGGER IF NOT EXISTS task_events_no_update
BEFORE UPDATE ON task_events
BEGIN
    SELECT RAISE(ABORT, 'task_events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS task_events_no_delete
BEFORE DELETE ON task_events
BEGIN
    SELECT RAISE(ABORT, 'task_events are immutable');
END;
"""

CLAIM_QUERY = """
SELECT
    queue_messages.message_id,
    queue_messages.task_id,
    tasks.version AS task_version
FROM queue_messages INDEXED BY idx_queue_claim
JOIN tasks ON tasks.task_id = queue_messages.task_id
WHERE queue_messages.available_at <= ?
  AND (queue_messages.leased_until IS NULL OR queue_messages.leased_until <= ?)
  AND tasks.status = ?
ORDER BY queue_messages.message_id
LIMIT 1
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class TaskDatabase:
    def __init__(
        self,
        path: Path | str,
        busy_timeout_ms: int = 5_000,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self.path = str(path)
        self.busy_timeout_ms = busy_timeout_ms
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=100)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1_000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Own one transaction-scoped connection and always close it."""
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            legacy_tables = {"tasks", "outbox", "queue_messages"}

            if version == 0 and legacy_tables.issubset(tables):
                self._migrate_unversioned_schema(connection)
                return
            if version == 0 and tables.intersection(legacy_tables):
                raise RuntimeError("partial unversioned E06 schema cannot be migrated safely")
            if version == 1:
                self._migrate_v1_schema(connection)
                return
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError(
                    f"unsupported E06 schema version {version}; expected {SCHEMA_VERSION}"
                )

            connection.executescript(SCHEMA_SQL)
            if version == 0:
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, timestamp(utc_now())),
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate_v1_schema(self, connection: sqlite3.Connection) -> None:
        """Upgrade the published v1 reference without losing task history."""
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.executescript(
                f"""
                BEGIN IMMEDIATE;
                DROP TRIGGER IF EXISTS task_events_no_update;
                DROP TRIGGER IF EXISTS task_events_no_delete;
                DROP INDEX IF EXISTS idx_outbox_unpublished;
                DROP INDEX IF EXISTS idx_queue_claim;
                DROP INDEX IF EXISTS idx_task_events_history;

                ALTER TABLE task_events RENAME TO task_events_v1;
                ALTER TABLE outbox RENAME TO outbox_v1;
                ALTER TABLE queue_messages RENAME TO queue_messages_v1;
                ALTER TABLE tasks RENAME TO tasks_v1;

                {SCHEMA_SQL}

                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json, result_json,
                    error_type, last_error, retry_count, max_retries, created_at,
                    queued_at, started_at, finished_at, version
                )
                SELECT
                    task_id, idempotency_key, status, input_json, result_json,
                    error_type, last_error, retry_count, max_retries, created_at,
                    queued_at, started_at, finished_at, version
                FROM tasks_v1;

                INSERT INTO outbox (
                    event_id, task_id, event_type, payload_json, created_at, published_at
                )
                SELECT event_id, task_id, event_type, payload_json, created_at, published_at
                FROM outbox_v1;

                INSERT INTO queue_messages (
                    message_id, task_id, available_at, leased_until, worker_id, delivery_count
                )
                SELECT message_id, task_id, available_at, leased_until, worker_id, delivery_count
                FROM queue_messages_v1;

                INSERT INTO task_events (
                    event_id, task_id, event_type, from_status, to_status,
                    task_version, worker_id, retry_count, created_at
                )
                SELECT
                    event_id, task_id, event_type, from_status, to_status,
                    task_version, worker_id, retry_count, created_at
                FROM task_events_v1;

                DROP TABLE queue_messages_v1;
                DROP TABLE outbox_v1;
                DROP TABLE task_events_v1;
                DROP TABLE tasks_v1;

                INSERT INTO schema_migrations(version, applied_at)
                VALUES ({SCHEMA_VERSION}, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                PRAGMA user_version = {SCHEMA_VERSION};
                COMMIT;
                """
            )
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

    def _migrate_unversioned_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.executescript(
                f"""
                BEGIN IMMEDIATE;
                ALTER TABLE outbox RENAME TO outbox_legacy;
                ALTER TABLE queue_messages RENAME TO queue_messages_legacy;
                ALTER TABLE tasks RENAME TO tasks_legacy;

                {SCHEMA_SQL}

                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json, result_json,
                    error_type, retry_count, max_retries, created_at, queued_at,
                    started_at, finished_at, version
                )
                SELECT
                    task_id, idempotency_key, status, input_json, result_json,
                    error_type, retry_count, max_retries, created_at, queued_at,
                    started_at, finished_at, version
                FROM tasks_legacy;

                INSERT INTO outbox (
                    event_id, task_id, event_type, payload_json, created_at, published_at
                )
                SELECT event_id, task_id, event_type, payload_json, created_at, published_at
                FROM outbox_legacy;

                INSERT INTO queue_messages (
                    message_id, task_id, available_at, leased_until, worker_id, delivery_count
                )
                SELECT message_id, task_id, available_at, leased_until, worker_id, delivery_count
                FROM queue_messages_legacy;

                INSERT INTO task_events (
                    task_id, event_type, from_status, to_status, task_version,
                    worker_id, retry_count, created_at
                )
                SELECT
                    task_id, 'task_migrated', NULL, status, version,
                    NULL, retry_count, created_at
                FROM tasks_legacy;

                DROP TABLE queue_messages_legacy;
                DROP TABLE outbox_legacy;
                DROP TABLE tasks_legacy;

                INSERT INTO schema_migrations(version, applied_at)
                VALUES ({SCHEMA_VERSION}, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
                PRAGMA user_version = {SCHEMA_VERSION};
                COMMIT;
                """
            )
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

    def schema_version(self) -> int:
        with self.connection() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def _record_transition(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        from_status: TaskStatus | str | None,
        to_status: TaskStatus | str,
        worker_id: str | None,
        current: datetime,
    ) -> None:
        task = connection.execute(
            "SELECT status, version, retry_count FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task is None or task["status"] != str(to_status):
            raise RuntimeError("cannot record an event for an unapplied transition")
        connection.execute(
            """
            INSERT INTO task_events (
                task_id, event_type, from_status, to_status, task_version,
                worker_id, retry_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                event_type,
                str(from_status) if from_status is not None else None,
                str(to_status),
                task["version"],
                worker_id,
                task["retry_count"],
                timestamp(current),
            ),
        )

    def submit_task(
        self,
        idempotency_key: str,
        input_json: dict,
        max_retries: int = 2,
        now: datetime | None = None,
        *,
        tenant_id: str = "reference-tenant",
        user_id: str = "reference-user",
        allowed_permission_groups: tuple[str, ...] = ("public",),
        acl_version: str = "reference-acl-v1",
        task_type: str = "reference_task",
        priority: int = 5,
        estimated_duration_ms: int = 0,
    ) -> tuple[str, bool]:
        current = now or utc_now()
        if not tenant_id or not user_id or not acl_version or not task_type:
            raise ValueError(
                "tenant_id, user_id, acl_version and task_type must be non-empty"
            )
        if not 1 <= priority <= 10:
            raise ValueError("priority must be between 1 and 10")
        if estimated_duration_ms < 0:
            raise ValueError("estimated_duration_ms must be non-negative")
        normalized_groups = tuple(sorted(set(allowed_permission_groups)))
        if not normalized_groups or any(not group for group in normalized_groups):
            raise ValueError("allowed_permission_groups must contain non-empty values")
        if not 0 <= max_retries <= self.retry_policy.max_attempts:
            raise ValueError(
                "max_retries must be non-negative and no greater than "
                "retry_policy.max_attempts"
            )
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT task_id FROM tasks
                WHERE tenant_id = ? AND user_id = ? AND idempotency_key = ?
                """,
                (tenant_id, user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return str(existing["task_id"]), False

            task_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, tenant_id, user_id, allowed_permission_groups_json,
                    acl_version, task_type, priority, estimated_duration_ms,
                    idempotency_key, status, input_json, max_retries, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    tenant_id,
                    user_id,
                    json.dumps(normalized_groups),
                    acl_version,
                    task_type,
                    priority,
                    estimated_duration_ms,
                    idempotency_key,
                    TaskStatus.PENDING,
                    json.dumps(input_json, ensure_ascii=False, sort_keys=True),
                    max_retries,
                    timestamp(current),
                ),
            )
            connection.execute(
                """
                INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                VALUES (?, 'task_submitted', ?, ?)
                """,
                (task_id, json.dumps({"task_id": task_id}), timestamp(current)),
            )
            self._record_transition(
                connection,
                task_id,
                "task_submitted",
                None,
                TaskStatus.PENDING,
                None,
                current,
            )
            return task_id, True

    def dispatch_outbox(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        dispatched = 0
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = connection.execute(
                """
                SELECT
                    outbox.event_id,
                    outbox.task_id,
                    outbox.event_type,
                    outbox.payload_json,
                    tasks.status AS from_status,
                    tasks.version AS task_version,
                    tasks.retry_count
                FROM outbox
                JOIN tasks ON tasks.task_id = outbox.task_id
                WHERE outbox.published_at IS NULL
                ORDER BY outbox.event_id
                """
            ).fetchall()
            for event in events:
                expected_source = {
                    "task_submitted": TaskStatus.PENDING,
                    "task_retry_requested": TaskStatus.RETRYING,
                }[event["event_type"]]
                if event["from_status"] != expected_source:
                    raise RuntimeError(
                        "outbox event source does not match the task state contract: "
                        f"{event['event_type']} requires {expected_source}, "
                        f"found {event['from_status']}"
                    )

                available_at = timestamp(current)
                if event["event_type"] == "task_retry_requested":
                    payload = json.loads(event["payload_json"])
                    if (
                        not isinstance(payload, dict)
                        or payload.get("retry_count") != event["retry_count"]
                        or not isinstance(payload.get("available_at"), str)
                    ):
                        raise RuntimeError("retry outbox payload does not match task state")
                    try:
                        retry_at = datetime.fromisoformat(payload["available_at"])
                    except ValueError as error:
                        raise RuntimeError("retry outbox has an invalid available_at") from error
                    if retry_at.tzinfo is None:
                        raise RuntimeError("retry outbox available_at must include a timezone")
                    available_at = timestamp(retry_at)

                connection.execute(
                    """
                    INSERT INTO queue_messages (task_id, available_at)
                    VALUES (?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        available_at = excluded.available_at,
                        leased_until = NULL,
                        worker_id = NULL
                    """,
                    (event["task_id"], available_at),
                )
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, queued_at = ?, version = version + 1
                    WHERE task_id = ? AND status = ? AND version = ?
                    """,
                    (
                        TaskStatus.QUEUED,
                        timestamp(current),
                        event["task_id"],
                        expected_source,
                        event["task_version"],
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("task state changed before outbox dispatch")
                self._record_transition(
                    connection,
                    event["task_id"],
                    "task_queued",
                    expected_source,
                    TaskStatus.QUEUED,
                    None,
                    current,
                )
                connection.execute(
                    "UPDATE outbox SET published_at = ? WHERE event_id = ?",
                    (timestamp(current), event["event_id"]),
                )
                dispatched += 1
        return dispatched

    def explain_claim_plan(self, now: datetime | None = None) -> list[str]:
        current = now or utc_now()
        with self.connection() as connection:
            rows = connection.execute(
                f"EXPLAIN QUERY PLAN {CLAIM_QUERY}",
                (timestamp(current), timestamp(current), TaskStatus.QUEUED),
            ).fetchall()
            return [str(row["detail"]) for row in rows]

    def claim_next(
        self,
        worker_id: str,
        lease_seconds: int = 30,
        now: datetime | None = None,
    ) -> dict | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = now or utc_now()
        lease_until = current + timedelta(seconds=lease_seconds)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            message = connection.execute(
                CLAIM_QUERY,
                (timestamp(current), timestamp(current), TaskStatus.QUEUED),
            ).fetchone()
            if message is None:
                return None

            queue_updated = connection.execute(
                """
                UPDATE queue_messages
                SET leased_until = ?, worker_id = ?, delivery_count = delivery_count + 1
                WHERE message_id = ?
                  AND (leased_until IS NULL OR leased_until <= ?)
                """,
                (
                    timestamp(lease_until),
                    worker_id,
                    message["message_id"],
                    timestamp(current),
                ),
            )
            if queue_updated.rowcount != 1:
                raise RuntimeError("queue lease changed before task claim")
            updated = connection.execute(
                """
                UPDATE tasks
                SET status = ?, started_at = ?, version = version + 1
                WHERE task_id = ? AND status = ? AND version = ?
                """,
                (
                    TaskStatus.RUNNING,
                    timestamp(current),
                    message["task_id"],
                    TaskStatus.QUEUED,
                    message["task_version"],
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("compare-and-set failed while claiming task")
            self._record_transition(
                connection,
                message["task_id"],
                "task_claimed",
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
                worker_id,
                current,
            )
            return self.get_task(message["task_id"], connection=connection)

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        lease_seconds: int = 30,
        now: datetime | None = None,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = now or utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE queue_messages
                SET leased_until = ?
                WHERE task_id = ? AND worker_id = ?
                  AND leased_until > ?
                  AND EXISTS (
                      SELECT 1 FROM tasks
                      WHERE tasks.task_id = queue_messages.task_id
                        AND tasks.status = ?
                        AND tasks.version = ?
                  )
                """,
                (
                    timestamp(current + timedelta(seconds=lease_seconds)),
                    task_id,
                    worker_id,
                    timestamp(current),
                    TaskStatus.RUNNING,
                    claim_version,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("heartbeat rejected for non-owner or non-running task")

    def reconcile_expired_leases(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        recovered = 0
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                """
                SELECT
                    queue_messages.task_id,
                    queue_messages.worker_id,
                    tasks.retry_count,
                    tasks.max_retries,
                    tasks.version
                FROM queue_messages
                JOIN tasks ON tasks.task_id = queue_messages.task_id
                WHERE tasks.status = ?
                  AND queue_messages.leased_until IS NOT NULL
                  AND queue_messages.leased_until <= ?
                """,
                (TaskStatus.RUNNING, timestamp(current)),
            ).fetchall()
            for row in expired:
                can_retry = row["retry_count"] < row["max_retries"]
                target = TaskStatus.QUEUED if can_retry else TaskStatus.FAILED
                if can_retry:
                    updated = connection.execute(
                        """
                        UPDATE tasks
                        SET status = ?, started_at = NULL, error_type = 'lease_expired',
                            last_error = 'worker lease expired',
                            retry_count = retry_count + 1, version = version + 1
                        WHERE task_id = ? AND status = ? AND version = ?
                          AND EXISTS (
                              SELECT 1 FROM queue_messages
                              WHERE queue_messages.task_id = tasks.task_id
                                AND queue_messages.worker_id = ?
                          )
                        """,
                        (
                            target,
                            row["task_id"],
                            TaskStatus.RUNNING,
                            row["version"],
                            row["worker_id"],
                        ),
                    )
                else:
                    updated = connection.execute(
                        """
                        UPDATE tasks
                        SET status = ?, error_type = 'lease_expired',
                            last_error = 'worker lease expired and recovery budget exhausted',
                            finished_at = ?, version = version + 1
                        WHERE task_id = ? AND status = ? AND version = ?
                          AND EXISTS (
                              SELECT 1 FROM queue_messages
                              WHERE queue_messages.task_id = tasks.task_id
                                AND queue_messages.worker_id = ?
                          )
                        """,
                        (
                            target,
                            timestamp(current),
                            row["task_id"],
                            TaskStatus.RUNNING,
                            row["version"],
                            row["worker_id"],
                        ),
                )
                if updated.rowcount != 1:
                    continue
                self._record_transition(
                    connection,
                    row["task_id"],
                    "lease_reconciled" if can_retry else "lease_recovery_exhausted",
                    TaskStatus.RUNNING,
                    target,
                    row["worker_id"],
                    current,
                )
                if can_retry:
                    retry_at = current + timedelta(
                        seconds=retry_delay_seconds(
                            row["task_id"],
                            row["retry_count"] + 1,
                            self.retry_policy,
                        )
                    )
                    connection.execute(
                        """
                        UPDATE queue_messages
                        SET available_at = ?, leased_until = NULL, worker_id = NULL
                        WHERE task_id = ?
                        """,
                        (timestamp(retry_at), row["task_id"]),
                    )
                else:
                    connection.execute(
                        "DELETE FROM queue_messages WHERE task_id = ?",
                        (row["task_id"],),
                    )
                recovered += 1
        return recovered

    def complete_task(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        result_json: dict,
        now: datetime | None = None,
    ) -> None:
        current = now or utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE tasks
                SET status = ?, result_json = ?, error_type = NULL, last_error = NULL,
                    finished_at = ?, version = version + 1
                WHERE task_id = ? AND status = ? AND version = ?
                  AND EXISTS (
                      SELECT 1 FROM queue_messages
                      WHERE queue_messages.task_id = tasks.task_id
                        AND queue_messages.worker_id = ?
                        AND queue_messages.leased_until > ?
                  )
                """,
                (
                    TaskStatus.SUCCEEDED,
                    json.dumps(result_json, ensure_ascii=False, sort_keys=True),
                    timestamp(current),
                    task_id,
                    TaskStatus.RUNNING,
                    claim_version,
                    worker_id,
                    timestamp(current),
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("compare-and-set failed while completing task")
            self._record_transition(
                connection,
                task_id,
                "task_succeeded",
                TaskStatus.RUNNING,
                TaskStatus.SUCCEEDED,
                worker_id,
                current,
            )
            connection.execute(
                "DELETE FROM queue_messages WHERE task_id = ? AND worker_id = ?",
                (task_id, worker_id),
            )

    def fail_task(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        error_type: str,
        now: datetime | None = None,
        error_message: str | None = None,
    ) -> TaskStatus:
        current = now or utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            retryable = int(error_type not in NON_RETRYABLE_ERRORS)
            task = connection.execute(
                """
                UPDATE tasks
                SET status = CASE
                        WHEN ? = 1 AND retry_count < max_retries THEN ?
                        ELSE ?
                    END,
                    error_type = ?,
                    last_error = ?,
                    retry_count = retry_count + CASE
                        WHEN ? = 1 AND retry_count < max_retries THEN 1
                        ELSE 0
                    END,
                    finished_at = CASE
                        WHEN ? = 1 AND retry_count < max_retries THEN NULL
                        ELSE ?
                    END,
                    version = version + 1
                WHERE task_id = ? AND status = ? AND version = ?
                  AND EXISTS (
                      SELECT 1 FROM queue_messages
                      WHERE queue_messages.task_id = tasks.task_id
                        AND queue_messages.worker_id = ?
                        AND queue_messages.leased_until > ?
                  )
                RETURNING status, retry_count
                """,
                (
                    retryable,
                    TaskStatus.RETRYING,
                    TaskStatus.FAILED,
                    error_type,
                    error_message or error_type,
                    retryable,
                    retryable,
                    timestamp(current),
                    task_id,
                    TaskStatus.RUNNING,
                    claim_version,
                    worker_id,
                    timestamp(current),
                ),
            ).fetchone()
            if task is None:
                raise RuntimeError("task is not owned by this claim or its lease expired")

            target = TaskStatus(task["status"])
            self._record_transition(
                connection,
                task_id,
                "task_retry_requested" if target == TaskStatus.RETRYING else "task_failed",
                TaskStatus.RUNNING,
                target,
                worker_id,
                current,
            )
            deleted = connection.execute(
                """
                DELETE FROM queue_messages
                WHERE task_id = ? AND worker_id = ? AND leased_until > ?
                """,
                (task_id, worker_id, timestamp(current)),
            )
            if deleted.rowcount != 1:
                raise RuntimeError("claim ownership changed before queue cleanup")

            if target == TaskStatus.RETRYING:
                retry_at = current + timedelta(
                    seconds=retry_delay_seconds(
                        task_id,
                        task["retry_count"],
                        self.retry_policy,
                    )
                )
                payload = {
                    "task_id": task_id,
                    "retry_count": task["retry_count"],
                    "available_at": timestamp(retry_at),
                }
                connection.execute(
                    """
                    INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                    VALUES (?, 'task_retry_requested', ?, ?)
                    """,
                    (
                        task_id,
                        json.dumps(payload, sort_keys=True),
                        timestamp(current),
                    ),
                )
            return target

    def get_task(
        self,
        task_id: str,
        connection: sqlite3.Connection | None = None,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict | None:
        if (tenant_id is None) != (user_id is None):
            raise ValueError("tenant_id and user_id must be supplied together")
        owns_connection = connection is None
        active_connection = connection or self.connect()
        try:
            if tenant_id is None:
                row = active_connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
            else:
                row = active_connection.execute(
                    """
                    SELECT * FROM tasks
                    WHERE task_id = ? AND tenant_id = ? AND user_id = ?
                    """,
                    (task_id, tenant_id, user_id),
                ).fetchone()
            return dict(row) if row is not None else None
        finally:
            if owns_connection:
                active_connection.close()

    def get_events(self, task_id: str) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_events
                WHERE task_id = ?
                ORDER BY task_version, event_id
                """,
                (task_id,),
            ).fetchall()
            return [dict(row) for row in rows]
