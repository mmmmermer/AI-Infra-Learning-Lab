from __future__ import annotations

import os
from uuid import uuid4

from locust import HttpUser, constant_throughput, task


class TaskSubmissionUser(HttpUser):
    wait_time = constant_throughput(
        float(os.getenv("P03_LOAD_REQUESTS_PER_USER", "5"))
    )

    @task
    def submit_task(self) -> None:
        task_type = os.getenv("P03_LOAD_TASK_TYPE", "mock_rag")
        if task_type not in {"mock_rag", "rag_retrieval"}:
            raise RuntimeError("P03_LOAD_TASK_TYPE must be mock_rag or rag_retrieval")
        input_json = {
            "query": os.getenv(
                "P03_LOAD_QUERY", "RAG 回答为什么需要来源引用？"
            ),
            "run_id": os.getenv("P03_LOAD_RUN_ID", "manual"),
        }
        if task_type == "mock_rag":
            input_json["sleep_ms"] = int(os.getenv("P03_LOAD_SLEEP_MS", "25"))
        else:
            input_json["top_k"] = int(os.getenv("P03_LOAD_TOP_K", "3"))
        payload = {
            "task_type": task_type,
            "priority": 5,
            "estimated_duration_ms": (
                int(os.getenv("P03_LOAD_SLEEP_MS", "25"))
                if task_type == "mock_rag"
                else 0
            ),
            "idempotency_key": f"locust-{uuid4()}",
            "input_json": input_json,
        }
        with self.client.post(
            "/tasks",
            json=payload,
            headers={"Authorization": "Bearer reference-ops-token"},
            name="POST /tasks",
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(f"unexpected status {response.status_code}")
                return
            data = response.json()
            if not data.get("created_new") or not data.get("task", {}).get("task_id"):
                response.failure("response lacks a newly created task_id")
