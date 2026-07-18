from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository import repository


ALICE_HEADERS = {"Authorization": "Bearer alice-fixture"}
BOB_HEADERS = {"Authorization": "Bearer bob-fixture"}
READER_HEADERS = {"Authorization": "Bearer reader-fixture"}
client = TestClient(app, headers=ALICE_HEADERS)


@pytest.fixture(autouse=True)
def clear_repository():
    repository.clear()
    yield
    repository.clear()


def test_create_then_query_task_and_observe_metrics():
    initial_metrics = client.get("/metrics")
    assert initial_metrics.status_code == 200
    assert initial_metrics.json()["task_count"] == 0

    created_response = client.post(
        "/tasks",
        json={"task_type": "rag_query", "priority": 2, "estimated_duration_ms": 1500},
    )
    assert created_response.status_code == 201
    created = created_response.json()
    UUID(created["task_id"])
    created_at = datetime.fromisoformat(created["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert created["status"] == "pending"
    assert "submit_time" not in created

    queried_response = client.get(f"/tasks/{created['task_id']}")
    assert queried_response.status_code == 200
    assert queried_response.json() == created

    metrics = client.get("/metrics").json()
    assert metrics["task_count"] == 1
    assert metrics["status_counts"]["pending"] == 1


def test_unknown_task_returns_stable_error():
    response = client.get("/tasks/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "task_not_found"}


def test_create_rejects_server_owned_fields():
    for field in (
        "task_id",
        "status",
        "submit_time",
        "created_at",
        "tenant_id",
        "user_id",
        "owner_id",
        "permission_group",
    ):
        response = client.post(
            "/tasks",
            json={
                "task_type": "rag_query",
                "priority": 2,
                "estimated_duration_ms": 100,
                field: "client-controlled",
            },
        )

        assert response.status_code == 422, field


def test_server_generates_distinct_task_ids_and_utc_times():
    payload = {
        "task_type": "rag_query",
        "priority": 2,
        "estimated_duration_ms": 100,
    }
    records = [client.post("/tasks", json=payload).json() for _ in range(2)]

    assert records[0]["task_id"] != records[1]["task_id"]
    for record in records:
        UUID(record["task_id"])
        created_at = datetime.fromisoformat(record["created_at"])
        assert created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("priority", [0, 11])
def test_create_rejects_invalid_priority(priority: int):
    response = client.post(
        "/tasks",
        json={
            "task_type": "rag_query",
            "priority": priority,
            "estimated_duration_ms": 100,
        },
    )

    assert response.status_code == 422


def test_create_rejects_negative_duration():
    response = client.post(
        "/tasks",
        json={
            "task_type": "rag_query",
            "priority": 2,
            "estimated_duration_ms": -1,
        },
    )

    assert response.status_code == 422


def test_create_requires_duration():
    response = client.post(
        "/tasks",
        json={"task_type": "rag_query", "priority": 2},
    )

    assert response.status_code == 422


def test_create_accepts_zero_duration():
    response = client.post(
        "/tasks",
        json={
            "task_type": "rag_query",
            "priority": 2,
            "estimated_duration_ms": 0,
        },
    )

    assert response.status_code == 201
    assert response.json()["estimated_duration_ms"] == 0


def test_authentication_and_scope_failures_are_distinct():
    payload = {
        "task_type": "rag_query",
        "priority": 2,
        "estimated_duration_ms": 100,
    }

    missing = TestClient(app).post("/tasks", json=payload)
    invalid = TestClient(
        app, headers={"Authorization": "Bearer invalid-fixture"}
    ).post("/tasks", json=payload)
    forbidden = client.post("/tasks", json=payload, headers=READER_HEADERS)

    assert (missing.status_code, missing.json()["detail"]) == (
        401,
        "authentication_required",
    )
    assert (invalid.status_code, invalid.json()["detail"]) == (
        401,
        "invalid_credentials",
    )
    assert (forbidden.status_code, forbidden.json()["detail"]) == (
        403,
        "insufficient_scope",
    )


def test_cross_owner_task_and_metrics_are_not_visible():
    created = client.post(
        "/tasks",
        json={
            "task_type": "rag_query",
            "priority": 2,
            "estimated_duration_ms": 100,
        },
    ).json()

    hidden = client.get(f"/tasks/{created['task_id']}", headers=BOB_HEADERS)
    bob_metrics = client.get("/metrics", headers=BOB_HEADERS)

    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "task_not_found"}
    assert bob_metrics.status_code == 200
    assert bob_metrics.json()["task_count"] == 0
