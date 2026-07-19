from contextlib import closing
import json
import sqlite3

from e06_reference import SCHEMA_VERSION, TaskDatabase


V1_SCHEMA = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    result_json TEXT,
    error_type TEXT,
    last_error TEXT,
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
CREATE TABLE task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    task_version INTEGER NOT NULL,
    worker_id TEXT,
    retry_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, task_version),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE INDEX idx_outbox_unpublished ON outbox(event_id);
CREATE INDEX idx_queue_claim ON queue_messages(available_at, leased_until, message_id, task_id);
CREATE INDEX idx_task_events_history ON task_events(task_id, task_version, event_id);
CREATE TRIGGER task_events_no_update BEFORE UPDATE ON task_events
BEGIN SELECT RAISE(ABORT, 'task_events are immutable'); END;
CREATE TRIGGER task_events_no_delete BEFORE DELETE ON task_events
BEGIN SELECT RAISE(ABORT, 'task_events are immutable'); END;
INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-07-18T00:00:00Z');
INSERT INTO tasks (
    task_id, idempotency_key, status, input_json, created_at, version
) VALUES ('v1-task', 'same-key', 'pending', '{"query":"old"}', '2026-07-18T00:00:00Z', 0);
INSERT INTO outbox (
    task_id, event_type, payload_json, created_at
) VALUES ('v1-task', 'task_submitted', '{"task_id":"v1-task"}', '2026-07-18T00:00:00Z');
INSERT INTO task_events (
    task_id, event_type, from_status, to_status, task_version, retry_count, created_at
) VALUES ('v1-task', 'task_submitted', NULL, 'pending', 0, 0, '2026-07-18T00:00:00Z');
PRAGMA user_version = 1;
"""


def test_v1_database_migrates_to_owner_scoped_v2_without_losing_history(tmp_path):
    path = tmp_path / "v1.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(V1_SCHEMA)

    database = TaskDatabase(path)
    migrated = database.get_task("v1-task")

    assert database.schema_version() == SCHEMA_VERSION == 2
    assert migrated is not None
    assert migrated["tenant_id"] == "reference-tenant"
    assert migrated["user_id"] == "reference-user"
    assert json.loads(migrated["allowed_permission_groups_json"]) == ["public"]
    assert migrated["acl_version"] == "reference-acl-v1"
    assert [event["event_type"] for event in database.get_events("v1-task")] == [
        "task_submitted"
    ]

    same_id, same_created = database.submit_task("same-key", {"query": "repeat"})
    other_id, other_created = database.submit_task(
        "same-key",
        {"query": "other owner"},
        tenant_id="reference-tenant",
        user_id="another-user",
    )

    assert (same_id, same_created) == ("v1-task", False)
    assert other_created is True
    assert other_id != same_id
    assert database.get_task(
        "v1-task", tenant_id="reference-tenant", user_id="another-user"
    ) is None

    with database.connection() as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [1, 2]
