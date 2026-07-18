from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str = Field(
        pattern=r"^(mock_rag|mock_agent|simulated_inference|rag_retrieval)$"
    )
    priority: int = Field(default=5, ge=1, le=10)
    estimated_duration_ms: int = Field(default=0, ge=0, le=86_400_000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    input_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_workload_input(self) -> "TaskCreate":
        security_keys = {
            "allowed_groups",
            "allowed_permission_groups",
            "permission_group",
            "permission_groups",
            "tenant_id",
            "user_id",
        }
        if security_keys.intersection(self.input_json):
            raise ValueError("security context must not be supplied in input_json")
        if self.task_type == "rag_retrieval":
            query = self.input_json.get("query")
            top_k = self.input_json.get("top_k", 3)
            if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1_000:
                raise ValueError("rag_retrieval requires a non-empty query")
            if (
                isinstance(top_k, bool)
                or not isinstance(top_k, int)
                or not 1 <= top_k <= 5
            ):
                raise ValueError("rag_retrieval top_k must be between 1 and 5")
        return self


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    tenant_id: str
    user_id: str
    allowed_permission_groups: tuple[str, ...]
    task_type: str
    priority: int
    estimated_duration_ms: int
    idempotency_key: str
    input_json: dict[str, Any]
    status: TaskStatus
    result_json: dict[str, Any] | None = None
    error_type: str | None = None
    created_at: datetime
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    runtime_ms: float | None = None
    version: int = Field(default=0, exclude=True)

    @computed_field
    @property
    def queue_wait_ms(self) -> float | None:
        if self.queued_at is None or self.started_at is None:
            return None
        return max(0.0, (self.started_at - self.queued_at).total_seconds() * 1_000)

    @computed_field
    @property
    def total_latency_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return max(0.0, (self.finished_at - self.created_at).total_seconds() * 1_000)


class SubmissionResponse(BaseModel):
    task: TaskRecord
    created_new: bool


class WorkerRunResponse(BaseModel):
    task_id: str
    status: TaskStatus
    error_type: str | None = None


class MetricsResponse(BaseModel):
    task_count: int
    broker_queue_length: int
    queue_length: int
    active_workers: int
    pending_outbox_count: int
    completed_last_minute: int
    status_counts: dict[TaskStatus, int]
    average_queue_wait_ms: float | None
    p95_queue_wait_ms: float | None
    p99_queue_wait_ms: float | None
    average_runtime_ms: float | None
    p95_runtime_ms: float | None
    p99_runtime_ms: float | None
    worker_busy_time_ms: float | None
    observation_window_ms: float | None
