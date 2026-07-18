import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag_workload import GOLD_QUERIES
from app.store import store


client = TestClient(app)
OPS = {"Authorization": "Bearer reference-ops-token"}
PUBLIC = {"Authorization": "Bearer reference-public-token"}
COMPLIANCE = {"Authorization": "Bearer reference-compliance-token"}
EMPTY = {"Authorization": "Bearer reference-empty-token"}
OTHER = {"Authorization": "Bearer reference-other-token"}


@pytest.fixture(autouse=True)
def clear_store():
    store.clear()
    yield
    store.clear()


def submit(
    key: str,
    *,
    headers: dict[str, str] = OPS,
    task_type: str = "mock_rag",
    **input_json,
):
    response = client.post(
        "/tasks",
        headers=headers,
        json={
            "task_type": task_type,
            "priority": 5,
            "estimated_duration_ms": 10,
            "idempotency_key": key,
            "input_json": input_json,
        },
    )
    assert response.status_code == 202
    return response.json()


def run_next():
    return client.post("/workers/run-next", headers=OPS)


def test_submit_run_query_and_metrics_closed_loop():
    submission = submit("request-1", query="what is rag")
    task_id = submission["task"]["task_id"]
    assert submission["task"]["status"] == "queued"
    assert client.get("/metrics", headers=OPS).json()["queue_length"] == 1

    completed = run_next()
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"
    assert "result_json" not in completed.json()

    queried = client.get(f"/tasks/{task_id}", headers=OPS).json()
    assert queried["result_json"]["quality_status"] == "not_evaluated"
    assert queried["runtime_ms"] >= 0
    assert queried["queue_wait_ms"] >= 0
    assert queried["total_latency_ms"] >= queried["runtime_ms"]

    metrics = client.get("/metrics", headers=OPS).json()
    assert metrics["queue_length"] == 0
    assert metrics["broker_queue_length"] == 0
    assert metrics["status_counts"]["succeeded"] == 1
    assert metrics["completed_last_minute"] == 1
    assert metrics["p95_queue_wait_ms"] >= 0
    assert metrics["p99_runtime_ms"] >= 0
    assert metrics["worker_busy_time_ms"] >= queried["runtime_ms"]
    assert metrics["observation_window_ms"] >= metrics["worker_busy_time_ms"]


def test_fifo_worker_order():
    first = submit("first", order=1)["task"]["task_id"]
    second = submit("second", order=2)["task"]["task_id"]

    assert run_next().json()["task_id"] == first
    assert run_next().json()["task_id"] == second


def test_idempotency_key_returns_existing_task_without_duplicate_queue_entry():
    first = submit("same-key", query="one")
    second = submit("same-key", query="changed input is ignored")

    assert first["task"]["task_id"] == second["task"]["task_id"]
    assert first["created_new"] is True
    assert second["created_new"] is False
    assert client.get("/metrics", headers=OPS).json()["queue_length"] == 1


def test_idempotency_and_task_reads_are_scoped_to_owner():
    public_task = submit("same-owner-key", headers=PUBLIC)
    compliance_task = submit("same-owner-key", headers=COMPLIANCE)

    assert public_task["task"]["task_id"] != compliance_task["task"]["task_id"]
    hidden = client.get(
        f"/tasks/{public_task['task']['task_id']}", headers=COMPLIANCE
    )
    assert hidden.status_code == 404


def test_worker_failure_is_recorded_and_queryable():
    task_id = submit("failure", force_error=True)["task"]["task_id"]

    failed = run_next().json()

    assert failed["status"] == "failed"
    assert failed["error_type"] == "forced_failure"
    assert client.get(f"/tasks/{task_id}", headers=OPS).json()["status"] == "failed"


def test_empty_worker_poll_is_explicitly_empty():
    response = run_next()

    assert response.status_code == 200
    assert response.json() is None


def test_invalid_mock_sleep_is_a_recorded_failure():
    submit("invalid-sleep", sleep_ms=5001)

    failed = run_next().json()

    assert failed["status"] == "failed"
    assert failed["error_type"] == "invalid_sleep_ms"


def test_metrics_can_be_isolated_by_run_id():
    submit("run-a", run_id="a", sleep_ms=1)
    submit("run-b", run_id="b", sleep_ms=1)
    run_next()
    run_next()

    run_a = client.get("/metrics", headers=OPS, params={"run_id": "a"}).json()
    all_runs = client.get("/metrics", headers=OPS).json()

    assert run_a["task_count"] == 1
    assert run_a["status_counts"]["succeeded"] == 1
    assert run_a["worker_busy_time_ms"] > 0
    assert all_runs["task_count"] == 2


def test_authentication_and_operator_endpoints_fail_closed():
    payload = {
        "task_type": "mock_rag",
        "priority": 5,
        "estimated_duration_ms": 0,
        "idempotency_key": "unauthenticated",
        "input_json": {},
    }
    assert client.post("/tasks", json=payload).status_code == 401
    assert client.get("/metrics", headers=PUBLIC).status_code == 403
    assert client.post("/workers/run-next", headers=PUBLIC).status_code == 403


@pytest.mark.parametrize(
    "forged_field",
    [
        "allowed_groups",
        "allowed_permission_groups",
        "permission_group",
        "permission_groups",
        "tenant_id",
        "user_id",
    ],
)
def test_payload_cannot_override_server_resolved_security_context(
    forged_field: str,
):
    response = client.post(
        "/tasks",
        headers=PUBLIC,
        json={
            "task_type": "rag_retrieval",
            "priority": 5,
            "estimated_duration_ms": 0,
            "idempotency_key": "permission-override",
            "input_json": {
                "query": "ZETA",
                forged_field: "attacker-controlled",
            },
        },
    )

    assert response.status_code == 422


def test_rag_permission_prefilter_rejects_unauthorized_private_source():
    task_id = submit(
        "rag-public",
        headers=PUBLIC,
        task_type="rag_retrieval",
        query="客户 ZETA 为什么需要额外人工复核？",
        top_k=5,
    )["task"]["task_id"]

    assert run_next().json()["status"] == "succeeded"
    result = client.get(f"/tasks/{task_id}", headers=PUBLIC).json()["result_json"]

    assert result["kind"] == "rag_retrieval_reference"
    assert result["security_context"] == {
        "tenant_id": "tenant-reference",
        "user_id": "user-public",
        "allowed_permission_groups": ["public"],
    }
    assert result["authorized_search_space_size"] > 0
    assert result["retrieval_status"] == "no_relevant_authorized_source"
    assert result["sources"] == []
    assert result["answer"] is None


def test_authorized_rag_persists_private_source_metadata():
    task_id = submit(
        "rag-compliance",
        headers=COMPLIANCE,
        task_type="rag_retrieval",
        query="客户 ZETA 为什么需要额外人工复核？",
        top_k=3,
    )["task"]["task_id"]

    run_next()
    task = client.get(f"/tasks/{task_id}", headers=COMPLIANCE).json()
    first_source = task["result_json"]["sources"][0]

    assert first_source["document_id"] == "doc_compliance_private_001"
    assert first_source["chunk_id"].startswith("doc_compliance_private_001#chunk-")
    assert first_source["permission_group"] == "compliance_private"
    assert first_source["tenant_id"] == "tenant-reference"
    assert first_source["text"]
    assert first_source["matched_query_token_count"] > 0


def test_rag_tenant_filter_excludes_other_tenant_document():
    public_id = submit(
        "rag-tenant-reference",
        headers=PUBLIC,
        task_type="rag_retrieval",
        query="OMEGA 项目",
        top_k=5,
    )["task"]["task_id"]
    other_id = submit(
        "rag-tenant-other",
        headers=OTHER,
        task_type="rag_retrieval",
        query="OMEGA 项目",
        top_k=1,
    )["task"]["task_id"]

    run_next()
    run_next()
    public_sources = client.get(f"/tasks/{public_id}", headers=PUBLIC).json()[
        "result_json"
    ]["sources"]
    other_sources = client.get(f"/tasks/{other_id}", headers=OTHER).json()[
        "result_json"
    ]["sources"]

    assert all(source["tenant_id"] == "tenant-reference" for source in public_sources)
    assert all(source["document_id"] != "doc_other_tenant_001" for source in public_sources)
    assert other_sources[0]["document_id"] == "doc_other_tenant_001"


def test_rag_empty_authorized_corpus_returns_explicit_empty_result():
    task_id = submit(
        "rag-empty",
        headers=EMPTY,
        task_type="rag_retrieval",
        query="任何内容",
        top_k=3,
    )["task"]["task_id"]

    run_next()
    result = client.get(f"/tasks/{task_id}", headers=EMPTY).json()["result_json"]

    assert result["authorized_search_space_size"] == 0
    assert result["retrieval_status"] == "empty_authorized_corpus"
    assert result["sources"] == []
    assert result["answer"] is None


def test_rag_fixed_golden_queries_retrieve_expected_source_end_to_end():
    headers_by_identity = {
        ("tenant-reference", ("public",)): PUBLIC,
        ("tenant-reference", ("compliance_private", "public")): COMPLIANCE,
        ("tenant-other", ("public",)): OTHER,
    }

    for gold in GOLD_QUERIES:
        headers = headers_by_identity[(gold.tenant_id, gold.permission_groups)]
        task_id = submit(
            f"gold-{gold.query_id}",
            headers=headers,
            task_type="rag_retrieval",
            query=gold.query,
            top_k=1,
        )["task"]["task_id"]
        run_next()
        result = client.get(f"/tasks/{task_id}", headers=headers).json()[
            "result_json"
        ]

        assert result["retrieval_status"] == "ok"
        assert result["sources"][0]["document_id"] == gold.expected_document_id
