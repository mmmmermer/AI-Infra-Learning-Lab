from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
from threading import Barrier, Lock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import AppContainer
from app.errors import AppError
from app.main import create_app
from app.rate_limit import FixedWindowRateLimiter
from app.repository import TaskRepository, repository as default_repository
from app.service import TaskService


ALICE_HEADERS = {"Authorization": "Bearer alice-fixture"}
BOB_HEADERS = {"Authorization": "Bearer bob-fixture"}
OTHER_TENANT_HEADERS = {"Authorization": "Bearer carol-fixture"}
PAYLOAD = {
    "task_type": "rag_query",
    "priority": 2,
    "estimated_duration_ms": 100,
}


class ManualClock:
    def __init__(self) -> None:
        self._value = 0.0
        self._lock = Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._value

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._value += seconds


def build_app(
    repository: TaskRepository,
    *,
    clock: ManualClock | None = None,
    limiter_capacity: int = 100,
):
    active_clock = clock or ManualClock()
    container = AppContainer(
        repository=repository,
        limiter=FixedWindowRateLimiter(
            capacity=limiter_capacity,
            window_seconds=1.0,
            clock=active_clock,
        ),
        clock=active_clock,
        now_factory=lambda: datetime(2026, 7, 18, tzinfo=timezone.utc),
    )
    return create_app(container)


def test_request_id_crosses_entry_security_service_repository_and_error(caplog):
    task_repository = TaskRepository()
    application = build_app(task_repository)
    client = TestClient(application, headers=ALICE_HEADERS)
    caplog.set_level(logging.INFO, logger="e02.audit")

    request_id = "trace-e02-001"
    response = client.get(
        "/tasks/not-visible",
        headers={**ALICE_HEADERS, "X-Request-ID": request_id},
    )

    assert response.status_code == 404
    assert response.headers["x-request-id"] == request_id
    assert response.json()["request_id"] == request_id
    stages = {
        getattr(record, "stage", None)
        for record in caplog.records
        if getattr(record, "request_id", None) == request_id
    }
    assert {"entry", "security", "service", "repository", "error_response"} <= stages

    rendered_records = "\n".join(repr(record.__dict__) for record in caplog.records)
    assert "alice-fixture" not in rendered_records
    assert "Authorization" not in rendered_records
    assert "tenant-demo" not in rendered_records


def test_unexpected_exception_logs_only_type_and_frame_locations(caplog):
    input_secret = "do-not-log-input-value"
    secret_values = (
        "alice-fixture",
        "Authorization",
        "tenant-demo",
        "do-not-log-secret-token",
        input_secret,
    )

    class ExplodingRepository(TaskRepository):
        def get_for_principal(self, *args, **kwargs):
            raise RuntimeError(f"{' '.join(secret_values)} task_id={args[0]}")

    application = build_app(ExplodingRepository())
    client = TestClient(
        application,
        headers=ALICE_HEADERS,
        raise_server_exceptions=False,
    )
    caplog.set_level(logging.INFO, logger="e02.audit")

    response = client.get(
        f"/tasks/{input_secret}",
        headers={**ALICE_HEADERS, "X-Request-ID": "trace-unexpected-001"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "internal_error"
    rendered_records = "\n".join(repr(record.__dict__) for record in caplog.records)
    for secret in secret_values:
        assert secret not in response.text
        assert secret not in rendered_records
    unexpected = next(
        record for record in caplog.records if record.getMessage() == "unexpected_error"
    )
    assert unexpected.exception_type == "RuntimeError"
    assert unexpected.exc_info is None
    assert unexpected.exception_frames
    assert any(
        frame.endswith(":get_for_principal")
        for frame in unexpected.exception_frames
    )


def test_app_container_injects_an_isolated_repository():
    default_repository.clear()
    isolated_repository = TaskRepository()
    application = build_app(isolated_repository)
    client = TestClient(application, headers=ALICE_HEADERS)

    response = client.post("/tasks", json=PAYLOAD)

    assert response.status_code == 201
    assert isolated_repository.count_all() == 1
    assert default_repository.count_all() == 0


def test_cross_tenant_read_list_metrics_and_logs_are_isolated(caplog):
    task_repository = TaskRepository()
    application = build_app(task_repository)
    alice = TestClient(application, headers=ALICE_HEADERS)
    other_tenant = TestClient(application, headers=OTHER_TENANT_HEADERS)
    created = alice.post("/tasks", json=PAYLOAD).json()
    caplog.clear()
    caplog.set_level(logging.INFO, logger="e02.audit")

    hidden = other_tenant.get(
        f"/tasks/{created['task_id']}",
        headers={**OTHER_TENANT_HEADERS, "X-Request-ID": "cross-tenant-read"},
    )
    unknown = other_tenant.get(
        "/tasks/not-present",
        headers={**OTHER_TENANT_HEADERS, "X-Request-ID": "cross-tenant-unknown"},
    )
    task_page = other_tenant.get(
        "/tasks",
        headers={**OTHER_TENANT_HEADERS, "X-Request-ID": "cross-tenant-list"},
    )
    metrics = other_tenant.get(
        "/metrics",
        headers={**OTHER_TENANT_HEADERS, "X-Request-ID": "cross-tenant-metrics"},
    )

    assert hidden.status_code == unknown.status_code == 404
    for field in ("type", "title", "status", "detail", "code"):
        assert hidden.json()[field] == unknown.json()[field]
    assert task_page.json() == {"items": [], "next_cursor": None}
    assert metrics.json()["task_count"] == 0
    assert set(metrics.json()["status_counts"].values()) == {0}
    response_text = "\n".join(
        response.text for response in (hidden, unknown, task_page, metrics)
    )
    audit_records = "\n".join(
        repr(record.__dict__)
        for record in caplog.records
        if record.name == "e02.audit"
    )
    for raw_value in (
        "alice-fixture",
        "carol-fixture",
        "Authorization",
        "tenant-demo",
        "tenant-other",
        "alice",
        "carol",
    ):
        assert raw_value not in response_text
        assert raw_value not in audit_records


def test_validation_error_is_machine_readable_and_does_not_echo_input():
    application = build_app(TaskRepository())
    client = TestClient(application, headers=ALICE_HEADERS)
    secret_like_input = "do-not-echo-this-value"

    response = client.post(
        "/tasks",
        json={**PAYLOAD, "owner_id": secret_like_input},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["status"] == 422
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["invalid_params"][0]["reason"] == "extra_forbidden"
    assert secret_like_input not in response.text


def test_readiness_tracks_dependency_and_pool_recovery():
    task_repository = TaskRepository(pool_size=1)
    application = build_app(task_repository)
    client = TestClient(application)

    task_repository.set_available(False)
    unavailable = client.get("/readyz")
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "dependency_unavailable"
    assert unavailable.headers["retry-after"] == "1"

    task_repository.set_available(True)
    assert client.get("/readyz").status_code == 200

    with task_repository.connection_lease():
        exhausted = client.get("/readyz")
    assert exhausted.status_code == 503
    assert exhausted.json()["code"] == "dependency_capacity_exhausted"
    assert client.get("/readyz").json() == {
        "status": "ready",
        "dependency": "task_repository",
    }


def test_dependency_loss_at_commit_aborts_write_and_recovers():
    fail_once = True
    task_repository: TaskRepository

    def fail_before_commit() -> None:
        nonlocal fail_once
        if fail_once:
            fail_once = False
            task_repository.set_available(False)

    task_repository = TaskRepository(before_commit=fail_before_commit)
    application = build_app(task_repository)
    client = TestClient(application, headers=ALICE_HEADERS)

    failed = client.post("/tasks", json=PAYLOAD)

    assert failed.status_code == 503
    assert failed.json()["code"] == "dependency_unavailable"
    assert task_repository.count_all() == 0
    assert client.get("/readyz").status_code == 503

    task_repository.set_available(True)
    recovered = client.post("/tasks", json=PAYLOAD)
    assert recovered.status_code == 201
    assert task_repository.count_all() == 1


def test_rate_limit_has_explicit_retry_and_recovers_after_window():
    clock = ManualClock()
    application = build_app(
        TaskRepository(clock=clock),
        clock=clock,
        limiter_capacity=1,
    )
    client = TestClient(application, headers=ALICE_HEADERS)

    assert client.post("/tasks", json=PAYLOAD).status_code == 201
    limited = client.post("/tasks", json=PAYLOAD)
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limit_exceeded"
    assert limited.json()["retry_after_ms"] == 1000
    assert limited.headers["retry-after"] == "1"

    clock.advance(1.0)
    assert client.post("/tasks", json=PAYLOAD).status_code == 201


def test_deadline_expiring_before_commit_leaves_no_ghost_write():
    clock = ManualClock()
    task_repository = TaskRepository(
        clock=clock,
        before_commit=lambda: clock.advance(0.020),
    )
    application = build_app(task_repository, clock=clock)
    client = TestClient(application, headers=ALICE_HEADERS)

    response = client.post(
        "/tasks",
        json=PAYLOAD,
        headers={
            **ALICE_HEADERS,
            "Idempotency-Key": "deadline-retry-001",
            "X-Request-Deadline-Ms": "10",
        },
    )

    assert response.status_code == 504
    assert response.json()["code"] == "deadline_exceeded"
    assert task_repository.count_all() == 0

    retry = client.post(
        "/tasks",
        json=PAYLOAD,
        headers={**ALICE_HEADERS, "Idempotency-Key": "deadline-retry-001"},
    )
    assert retry.status_code == 201
    assert retry.headers["idempotency-replayed"] == "false"
    assert task_repository.count_all() == 1


def test_deadline_expiring_before_update_commit_preserves_version_and_value():
    clock = ManualClock()
    expire_update = False

    def advance_during_commit() -> None:
        if expire_update:
            clock.advance(0.020)

    task_repository = TaskRepository(
        clock=clock,
        before_commit=advance_during_commit,
    )
    application = build_app(task_repository, clock=clock)
    client = TestClient(application, headers=ALICE_HEADERS)
    created = client.post("/tasks", json=PAYLOAD).json()
    expire_update = True

    failed = client.patch(
        f"/tasks/{created['task_id']}",
        json={"priority": 7},
        headers={
            **ALICE_HEADERS,
            "If-Match": '"1"',
            "X-Request-Deadline-Ms": "10",
        },
    )

    assert failed.status_code == 504
    assert failed.json()["code"] == "deadline_exceeded"
    current = client.get(f"/tasks/{created['task_id']}").json()
    assert (current["priority"], current["version"]) == (2, 1)


def test_idempotent_create_replays_once_and_rejects_payload_conflict():
    task_repository = TaskRepository()
    application = build_app(task_repository)
    client = TestClient(application, headers=ALICE_HEADERS)
    headers = {**ALICE_HEADERS, "Idempotency-Key": "create-rag-query-001"}

    first = client.post("/tasks", json=PAYLOAD, headers=headers)
    replay = client.post("/tasks", json=PAYLOAD, headers=headers)
    conflict = client.post(
        "/tasks",
        json={**PAYLOAD, "priority": 3},
        headers=headers,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json()["task_id"] == first.json()["task_id"]
    assert task_repository.count_all() == 1
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_conflict"


def test_concurrent_idempotent_creates_commit_exactly_once():
    task_repository = TaskRepository()
    application = build_app(task_repository, limiter_capacity=10)
    start = Barrier(2)
    headers = {**ALICE_HEADERS, "Idempotency-Key": "concurrent-create-001"}

    def create_once(_index: int):
        with TestClient(application, headers=ALICE_HEADERS) as client:
            start.wait(timeout=5)
            return client.post("/tasks", json=PAYLOAD, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(create_once, range(2)))

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert {response.json()["task_id"] for response in responses} == {
        responses[0].json()["task_id"]
    }
    assert sorted(
        response.headers["idempotency-replayed"] for response in responses
    ) == ["false", "true"]
    assert task_repository.count_all() == 1


def test_mutations_and_idempotency_keys_are_owner_and_tenant_scoped():
    task_repository = TaskRepository()
    application = build_app(task_repository, limiter_capacity=20)
    client = TestClient(application, headers=ALICE_HEADERS)
    shared_key = "same-visible-string"
    alice = client.post(
        "/tasks",
        json=PAYLOAD,
        headers={**ALICE_HEADERS, "Idempotency-Key": shared_key},
    )
    bob = client.post(
        "/tasks",
        json=PAYLOAD,
        headers={**BOB_HEADERS, "Idempotency-Key": shared_key},
    )
    carol = client.post(
        "/tasks",
        json=PAYLOAD,
        headers={**OTHER_TENANT_HEADERS, "Idempotency-Key": shared_key},
    )

    assert [alice.status_code, bob.status_code, carol.status_code] == [201, 201, 201]
    assert len({alice.json()["task_id"], bob.json()["task_id"], carol.json()["task_id"]}) == 3
    assert task_repository.count_all() == 3

    hidden_updates = [
        client.patch(
            f"/tasks/{alice.json()['task_id']}",
            json={"priority": 9},
            headers={**headers, "If-Match": '"1"'},
        )
        for headers in (BOB_HEADERS, OTHER_TENANT_HEADERS)
    ]
    unknown = client.patch(
        "/tasks/not-present",
        json={"priority": 9},
        headers={**BOB_HEADERS, "If-Match": '"1"'},
    )
    for response in [*hidden_updates, unknown]:
        assert response.status_code == 404
        assert response.json()["code"] == "task_not_found"

    unchanged = client.get(f"/tasks/{alice.json()['task_id']}").json()
    assert (unchanged["priority"], unchanged["version"]) == (2, 1)


def test_concurrent_updates_use_version_compare_and_swap():
    task_repository = TaskRepository()
    application = build_app(task_repository, limiter_capacity=10)
    creator = TestClient(application, headers=ALICE_HEADERS)
    created = creator.post("/tasks", json=PAYLOAD)
    task_id = created.json()["task_id"]

    def update(priority: int):
        with TestClient(application, headers=ALICE_HEADERS) as client:
            return client.patch(
                f"/tasks/{task_id}",
                json={"priority": priority},
                headers={**ALICE_HEADERS, "If-Match": '"1"'},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(update, [4, 7]))

    assert sorted(response.status_code for response in responses) == [200, 412]
    winner = next(response for response in responses if response.status_code == 200)
    loser = next(response for response in responses if response.status_code == 412)
    assert winner.json()["version"] == 2
    assert winner.headers["etag"] == '"2"'
    assert loser.json()["code"] == "version_conflict"

    current = creator.get(f"/tasks/{task_id}")
    assert current.json()["version"] == 2
    assert current.json()["priority"] in {4, 7}


def test_cursor_pagination_is_stable_owner_scoped_and_machine_readable():
    task_repository = TaskRepository()
    application = build_app(task_repository)
    alice = TestClient(application, headers=ALICE_HEADERS)
    bob_headers = {"Authorization": "Bearer bob-fixture"}
    for priority in (1, 2, 3):
        assert alice.post(
            "/tasks",
            json={**PAYLOAD, "priority": priority},
        ).status_code == 201

    first = alice.get("/tasks", params={"limit": 2})
    second = alice.get(
        "/tasks",
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )
    bob = alice.get("/tasks", headers=bob_headers)
    invalid = alice.get("/tasks", params={"cursor": "not-a-visible-cursor"})
    tampered = alice.get(
        "/tasks",
        params={"cursor": f"!!!!{first.json()['next_cursor']}!!!!"},
    )

    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert first.json()["next_cursor"] is not None
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
    assert bob.json() == {"items": [], "next_cursor": None}
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_cursor"
    assert tampered.status_code == 400
    assert tampered.json()["code"] == "invalid_cursor"


def test_cursor_decoder_rejects_noncanonical_base64url_alias():
    assert TaskService._encode_cursor("f") == "Zg"
    assert TaskService._decode_cursor("Zg") == "f"

    with pytest.raises(AppError) as error:
        TaskService._decode_cursor("Zh")

    assert error.value.code == "invalid_cursor"
