from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str
    task_type: str
    priority: int
    estimated_duration: float
    submit_time: float
    token_count: int = 0
    actual_duration: float | None = None
    start_time: float | None = None
    finish_time: float | None = None
    status: TaskStatus = TaskStatus.PENDING

    @property
    def service_duration(self) -> float:
        duration = self.actual_duration if self.actual_duration is not None else self.estimated_duration
        if duration < 0:
            raise ValueError(f"task {self.id} duration must be non-negative")
        return duration


@dataclass
class Worker:
    id: str
    available_at: float = 0.0
    current_task_id: str | None = None
    total_busy_time: float = 0.0
