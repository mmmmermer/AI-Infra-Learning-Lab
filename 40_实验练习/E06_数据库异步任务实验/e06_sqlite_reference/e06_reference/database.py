from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


NON_RETRYABLE_ERRORS = {"collection_not_found", "invalid_input", "permission_denied"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class TaskDatabase:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    result_json TEXT,
                    error_type TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    created_at TEXT NOT NULL,
                    queued_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    version INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS outbox (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
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
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );
                """
            )

    def submit_task(
        self,
        idempotency_key: str,
        input_json: dict,
        max_retries: int = 2,
        now: datetime | None = None,
    ) -> tuple[str, bool]:
        current = now or utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT task_id FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return str(existing["task_id"]), False

            task_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json, max_retries, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
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
            return task_id, True

    def dispatch_outbox(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        dispatched = 0
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = connection.execute(
                "SELECT event_id, task_id FROM outbox WHERE published_at IS NULL ORDER BY event_id"
            ).fetchall()
            for event in events:
                connection.execute(
                    """
                    INSERT INTO queue_messages (task_id, available_at)
                    VALUES (?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        available_at = excluded.available_at,
                        leased_until = NULL,
                        worker_id = NULL
                    """,
                    (event["task_id"], timestamp(current)),
                )
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, queued_at = ?, version = version + 1
                    WHERE task_id = ? AND status IN (?, ?)
                    """,
                    (
                        TaskStatus.QUEUED,
                        timestamp(current),
                        event["task_id"],
                        TaskStatus.PENDING,
                        TaskStatus.RETRYING,
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("task state changed before outbox dispatch")
                connection.execute(
                    "UPDATE outbox SET published_at = ? WHERE event_id = ?",
                    (timestamp(current), event["event_id"]),
                )
                dispatched += 1
        return dispatched

    def claim_next(
        self,
        worker_id: str,
        lease_seconds: int = 30,
        now: datetime | None = None,
    ) -> dict | None:
        current = now or utc_now()
        lease_until = current + timedelta(seconds=lease_seconds)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            message = connection.execute(
                """
                SELECT queue_messages.message_id, queue_messages.task_id
                FROM queue_messages
                JOIN tasks ON tasks.task_id = queue_messages.task_id
                WHERE queue_messages.available_at <= ?
                  AND (queue_messages.leased_until IS NULL OR queue_messages.leased_until <= ?)
                  AND tasks.status = ?
                ORDER BY message_id
                LIMIT 1
                """,
                (timestamp(current), timestamp(current), TaskStatus.QUEUED),
            ).fetchone()
            if message is None:
                return None

            connection.execute(
                """
                UPDATE queue_messages
                SET leased_until = ?, worker_id = ?, delivery_count = delivery_count + 1
                WHERE message_id = ?
                """,
                (timestamp(lease_until), worker_id, message["message_id"]),
            )
            updated = connection.execute(
                """
                UPDATE tasks
                SET status = ?, started_at = ?, version = version + 1
                WHERE task_id = ? AND status = ?
                """,
                (TaskStatus.RUNNING, timestamp(current), message["task_id"], TaskStatus.QUEUED),
            )
            if updated.rowcount != 1:
                raise RuntimeError("compare-and-set failed while claiming task")
            return self.get_task(message["task_id"], connection=connection)

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        lease_seconds: int = 30,
        now: datetime | None = None,
    ) -> None:
        current = now or utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE queue_messages
                SET leased_until = ?
                WHERE task_id = ? AND worker_id = ?
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
                    TaskStatus.RUNNING,
                    claim_version,
                ),
            )
            if updated.rowcount != 1:
                raise RuntimeError("heartbeat rejected for non-owner or non-running task")

    def reconcile_expired_leases(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                """
                SELECT queue_messages.task_id
                FROM queue_messages
                JOIN tasks ON tasks.task_id = queue_messages.task_id
                WHERE tasks.status = ?
                  AND queue_messages.leased_until IS NOT NULL
                  AND queue_messages.leased_until <= ?
                """,
                (TaskStatus.RUNNING, timestamp(current)),
            ).fetchall()
            for row in expired:
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, started_at = NULL, version = version + 1
                    WHERE task_id = ? AND status = ?
                    """,
                    (TaskStatus.QUEUED, row["task_id"], TaskStatus.RUNNING),
                )
                connection.execute(
                    """
                    UPDATE queue_messages
                    SET leased_until = NULL, worker_id = NULL
                    WHERE task_id = ?
                    """,
                    (row["task_id"],),
                )
            return len(expired)

    def complete_task(
        self,
        task_id: str,
        worker_id: str,
        claim_version: int,
        result_json: dict,
        now: datetime | None = None,
    ) -> None:
        current = now or utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE tasks
                SET status = ?, result_json = ?, error_type = NULL,
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
    ) -> TaskStatus:
        current = now or utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            task = connection.execute(
                """
                SELECT tasks.retry_count, tasks.max_retries, tasks.status, tasks.version
                FROM tasks
                JOIN queue_messages ON queue_messages.task_id = tasks.task_id
                WHERE tasks.task_id = ? AND queue_messages.worker_id = ?
                  AND queue_messages.leased_until > ?
                """,
                (task_id, worker_id, timestamp(current)),
            ).fetchone()
            if (
                task is None
                or task["status"] != TaskStatus.RUNNING
                or task["version"] != claim_version
            ):
                raise RuntimeError("task is not owned by this claim or its lease expired")

            retryable = error_type not in NON_RETRYABLE_ERRORS
            if retryable and task["retry_count"] < task["max_retries"]:
                target = TaskStatus.RETRYING
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, error_type = ?, retry_count = retry_count + 1,
                        version = version + 1
                    WHERE task_id = ? AND status = ? AND version = ?
                    """,
                    (target, error_type, task_id, TaskStatus.RUNNING, claim_version),
                )
                connection.execute(
                    "DELETE FROM queue_messages WHERE task_id = ? AND worker_id = ?",
                    (task_id, worker_id),
                )
                connection.execute(
                    """
                    INSERT INTO outbox (task_id, event_type, payload_json, created_at)
                    VALUES (?, 'task_retry_requested', ?, ?)
                    """,
                    (task_id, json.dumps({"task_id": task_id}), timestamp(current)),
                )
            else:
                target = TaskStatus.FAILED
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, error_type = ?, finished_at = ?, version = version + 1
                    WHERE task_id = ? AND status = ? AND version = ?
                    """,
                    (
                        target,
                        error_type,
                        timestamp(current),
                        task_id,
                        TaskStatus.RUNNING,
                        claim_version,
                    ),
                )
                connection.execute(
                    "DELETE FROM queue_messages WHERE task_id = ? AND worker_id = ?",
                    (task_id, worker_id),
                )
            return target

    def get_task(
        self, task_id: str, connection: sqlite3.Connection | None = None
    ) -> dict | None:
        owns_connection = connection is None
        active_connection = connection or self.connect()
        try:
            row = active_connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return dict(row) if row is not None else None
        finally:
            if owns_connection:
                active_connection.close()
