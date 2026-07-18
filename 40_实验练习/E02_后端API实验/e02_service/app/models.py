from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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

    task_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    priority: int = Field(default=5, ge=1, le=10)
    estimated_duration_ms: int = Field(ge=0, le=86_400_000)


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1, le=10)


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: str
    priority: int
    estimated_duration_ms: int
    status: TaskStatus
    created_at: datetime
    version: int = Field(ge=1)


class MetricsResponse(BaseModel):
    task_count: int
    status_counts: dict[TaskStatus, int]


class TaskPage(BaseModel):
    items: list[TaskRecord]
    next_cursor: str | None


class HealthResponse(BaseModel):
    status: str
    dependency: str


class InvalidParameter(BaseModel):
    location: list[str | int]
    reason: str


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str
    retry_after_ms: int | None = None
    invalid_params: list[InvalidParameter] | None = None
