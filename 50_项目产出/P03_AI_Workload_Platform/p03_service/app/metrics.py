from __future__ import annotations

from dataclasses import dataclass

from .models import TaskStatus


@dataclass(frozen=True)
class TaskMetricsSnapshot:
    task_count: int
    status_counts: dict[TaskStatus, int]
    average_queue_wait_ms: float | None
    p95_queue_wait_ms: float | None
    p99_queue_wait_ms: float | None
    average_runtime_ms: float | None
    p95_runtime_ms: float | None
    p99_runtime_ms: float | None
    worker_busy_time_ms: float | None
    observation_window_ms: float | None
    completed_last_minute: int
    pending_outbox_count: int


def linear_percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
