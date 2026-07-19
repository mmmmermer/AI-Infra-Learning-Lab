from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient

from e06_reference import (
    AuthorizedScope,
    MemoryCacheBackend,
    Principal,
    ReferenceWorker,
    RetrievalRequest,
    RetrievalResult,
    SafeRetrievalCache,
    TaskDatabase,
    TaskFailure,
    TaskStatus,
)
from e06_reference.api import create_app


NOW = datetime(2026, 7, 19, 16, 0, tzinfo=timezone.utc)
PUBLIC_HEADERS = {"Authorization": "Bearer reference-public-token"}
COMPLIANCE_HEADERS = {"Authorization": "Bearer reference-compliance-token"}
OTHER_TENANT_HEADERS = {
    "Authorization": "Bearer reference-other-tenant-token"
}


def payload(idempotency_key: str, *, collection_id: str = "demo_docs") -> dict:
    return {
        "task_type": "rag_retrieval",
        "priority": 5,
        "estimated_duration_ms": 20,
        "idempotency_key": idempotency_key,
        "input_json": {
            "query": "RAG why sources",
            "collection_id": collection_id,
            "top_k": 2,
        },
    }


@pytest.fixture
def database(tmp_path):
    return TaskDatabase(tmp_path / "api.db")


@pytest.fixture
def client(database):
    with TestClient(create_app(database), headers=PUBLIC_HEADERS) as test_client:
        yield test_client


def test_api_authenticates_and_persists_server_owned_principal(client, database):
    missing = TestClient(client.app).post("/tasks", json=payload("missing-auth"))
    invalid = client.post(
        "/tasks",
        json=payload("invalid-auth"),
        headers={"Authorization": "Bearer invalid"},
    )
    created = client.post("/tasks", json=payload("same-request"))
    repeated = client.post("/tasks", json=payload("same-request"))

    assert (missing.status_code, missing.json()["detail"]) == (
        401,
        "authentication_required",
    )
    assert (invalid.status_code, invalid.json()["detail"]) == (
        401,
        "invalid_credentials",
    )
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["created_new"] is False
    assert repeated.json()["task"]["task_id"] == created.json()["task"]["task_id"]

    task = database.get_task(created.json()["task"]["task_id"])
    assert task is not None
    assert task["tenant_id"] == "tenant-reference"
    assert task["user_id"] == "user-public"
    assert json.loads(task["allowed_permission_groups_json"]) == ["public"]
    assert task["acl_version"] == "acl-v1"


def test_forged_identity_fields_are_rejected_without_database_writes(client, database):
    fields = (
        "tenant_id",
        "user_id",
        "permission_group",
        "permission_groups",
        "allowed_permission_groups",
        "acl_version",
    )
    for field in fields:
        top_level = payload(f"top-{field}")
        top_level[field] = "forged"
        nested = payload(f"nested-{field}")
        nested["input_json"][field] = "forged"

        assert client.post("/tasks", json=top_level).status_code == 422
        assert client.post("/tasks", json=nested).status_code == 422

    with database.connection() as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "outbox", "task_events")
        }
    assert counts == {"tasks": 0, "outbox": 0, "task_events": 0}


def test_idempotency_and_queries_are_owner_scoped(client):
    public = client.post("/tasks", json=payload("shared-key")).json()["task"]
    compliance = client.post(
        "/tasks", json=payload("shared-key"), headers=COMPLIANCE_HEADERS
    ).json()["task"]

    assert public["task_id"] != compliance["task_id"]
    assert client.get(
        f"/tasks/{public['task_id']}", headers=COMPLIANCE_HEADERS
    ).status_code == 404
    assert client.get(
        f"/tasks/{public['task_id']}", headers=OTHER_TENANT_HEADERS
    ).status_code == 404
    assert client.get(f"/tasks/{public['task_id']}").status_code == 200


def test_fastapi_database_worker_and_safe_cache_form_an_end_to_end_loop(
    client, database
):
    first = client.post("/tasks", json=payload("run-1")).json()["task"]
    second = client.post("/tasks", json=payload("run-2")).json()["task"]
    assert database.dispatch_outbox(now=NOW) == 2

    cache = SafeRetrievalCache(MemoryCacheBackend())
    compute_calls = 0

    def handler(task):
        nonlocal compute_calls
        principal = Principal(
            task["tenant_id"],
            task["user_id"],
            tuple(json.loads(task["allowed_permission_groups_json"])),
            task["acl_version"],
        )
        input_json = json.loads(task["input_json"])
        request = RetrievalRequest(
            input_json["query"],
            input_json["collection_id"],
            input_json["top_k"],
        )

        def authorize(active_principal, active_request):
            source_ids = ["doc-public"]
            if "compliance_private" in active_principal.permission_groups:
                source_ids.append("doc-private")
            return AuthorizedScope(
                active_request.collection_id,
                tuple(source_ids),
                "docs-v1",
                "index-v1",
                "embed-v1",
                "bm25-v1",
            )

        def compute(scope, active_request):
            nonlocal compute_calls
            compute_calls += 1
            return RetrievalResult("supported answer", scope.source_ids[:1])

        outcome = cache.retrieve(
            principal,
            request,
            authorize=authorize,
            compute=compute,
        )
        return {
            "answer": outcome.result.answer,
            "retrieved_sources": list(outcome.result.source_ids),
            "metrics": {
                "retrieval_cache_hit": outcome.cache_hit,
                "cache_unavailable": outcome.cache_unavailable,
                "cache_value_invalid": outcome.cache_value_invalid,
            },
        }

    worker = ReferenceWorker(
        database,
        worker_id="worker-e06",
        now_factory=lambda: NOW,
    )
    assert worker.run_once(handler).status == TaskStatus.SUCCEEDED
    assert worker.run_once(handler).status == TaskStatus.SUCCEEDED
    assert worker.run_once(handler) is None

    first_result = client.get(f"/tasks/{first['task_id']}").json()
    second_result = client.get(f"/tasks/{second['task_id']}").json()
    assert first_result["status"] == second_result["status"] == "succeeded"
    assert first_result["result_json"]["metrics"]["retrieval_cache_hit"] is False
    assert second_result["result_json"]["metrics"]["retrieval_cache_hit"] is True
    assert first_result["result_json"]["retrieved_sources"] == ["doc-public"]
    assert compute_calls == 1


def test_worker_fixture_records_non_retryable_failure(client, database):
    created = client.post(
        "/tasks", json=payload("missing-collection", collection_id="missing")
    ).json()["task"]
    database.dispatch_outbox(now=NOW)
    worker = ReferenceWorker(
        database,
        worker_id="worker-failure",
        now_factory=lambda: NOW,
    )

    run = worker.run_once(
        lambda task: (_ for _ in ()).throw(
            TaskFailure("collection_not_found", "collection does not exist")
        )
    )
    observed = client.get(f"/tasks/{created['task_id']}").json()

    assert run.status == TaskStatus.FAILED
    assert observed["status"] == "failed"
    assert observed["error_type"] == "collection_not_found"
    assert observed["retry_count"] == 0


def test_openapi_forbids_extra_identity_fields(client):
    schema = client.get("/openapi.json").json()

    assert schema["components"]["schemas"]["CreateTaskRequest"][
        "additionalProperties"
    ] is False
    assert schema["components"]["schemas"]["RagTaskInput"][
        "additionalProperties"
    ] is False
