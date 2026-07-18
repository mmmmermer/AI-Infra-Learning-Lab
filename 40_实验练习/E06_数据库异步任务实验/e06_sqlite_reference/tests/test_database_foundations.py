from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from e06_reference import SCHEMA_VERSION, TaskDatabase, TaskStatus


NOW = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)


def test_schema_constraints_reject_invalid_state_and_retry_count(tmp_path):
    database = TaskDatabase(tmp_path / "constraints.db")
    assert database.schema_version() == SCHEMA_VERSION

    with database.connection() as connection:
        migration = connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchone()
        assert migration["version"] == SCHEMA_VERSION

        values = (
            "task-invalid",
            "invalid-key",
            "not-a-state",
            json.dumps({"query": "test"}),
            NOW.isoformat(),
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                values,
            )

        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json,
                    retry_count, max_retries, created_at
                ) VALUES ('task-retry', 'retry-key', 'pending', '{}', 2, 1, ?)
                """,
                (NOW.isoformat(),),
            )

        with pytest.raises(sqlite3.IntegrityError, match="json_valid"):
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, idempotency_key, status, input_json, created_at
                ) VALUES ('task-json', 'json-key', 'pending', '{', ?)
                """,
                (NOW.isoformat(),),
            )

        connection.execute(
            """
            INSERT INTO tasks (
                task_id, idempotency_key, status, input_json, created_at
            ) VALUES ('task-lease', 'lease-key', 'pending', '{}', ?)
            """,
            (NOW.isoformat(),),
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute(
                """
                INSERT INTO queue_messages (task_id, available_at, leased_until)
                VALUES ('task-lease', ?, ?)
                """,
                (NOW.isoformat(), NOW.isoformat()),
            )


@pytest.mark.parametrize(
    ("legacy_status", "should_migrate"),
    [("pending", True), ("invented-state", False)],
)
def test_unversioned_reference_schema_migration_is_atomic(
    tmp_path, legacy_status, should_migrate
):
    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE tasks (
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
            CREATE TABLE outbox (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                published_at TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE queue_messages (
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
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, idempotency_key, status, input_json, created_at
            ) VALUES ('legacy-task', 'legacy-key', ?, '{}', '2026-07-18T08:00:00+00:00')
            """,
            (legacy_status,),
        )

    if not should_migrate:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            TaskDatabase(path)
        with closing(sqlite3.connect(path)) as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert "tasks" in names
            assert "tasks_legacy" not in names
            assert connection.execute(
                "SELECT status FROM tasks WHERE task_id = 'legacy-task'"
            ).fetchone()[0] == legacy_status
        return

    database = TaskDatabase(path)

    assert database.schema_version() == SCHEMA_VERSION
    assert database.get_task("legacy-task")["status"] == TaskStatus.PENDING
    events = database.get_events("legacy-task")
    assert [(event["event_type"], event["to_status"]) for event in events] == [
        ("task_migrated", TaskStatus.PENDING)
    ]


def test_claim_query_plan_uses_declared_index(tmp_path):
    database = TaskDatabase(tmp_path / "plan.db")
    task_id, _ = database.submit_task("plan", {}, now=NOW)
    database.dispatch_outbox(now=NOW)

    plan = database.explain_claim_plan(now=NOW)

    assert any("idx_queue_claim" in step for step in plan), plan
    assert database.get_task(task_id)["status"] == TaskStatus.QUEUED


def test_sqlite_writer_lock_fails_bounded_then_recovers(tmp_path):
    database = TaskDatabase(tmp_path / "lock.db", busy_timeout_ms=20)
    blocker = database.connect()
    try:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            database.submit_task("blocked", {}, now=NOW)
        blocker.rollback()

        task_id, created = database.submit_task("recovered", {}, now=NOW)
        assert created is True
        assert database.get_task(task_id)["status"] == TaskStatus.PENDING
    finally:
        blocker.close()


def test_owned_connections_close_and_database_file_can_be_deleted(tmp_path):
    path = tmp_path / "closed.db"
    database = TaskDatabase(path)
    task_id, _ = database.submit_task("close-check", {}, now=NOW)
    database.dispatch_outbox(now=NOW)
    database.explain_claim_plan(now=NOW)
    assert database.get_task(task_id)["status"] == TaskStatus.QUEUED

    with database.connection() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")

    path.unlink()
    assert not path.exists()
