from __future__ import annotations

import math

from .models import Task, Worker


def calculate_wait_time(task: Task) -> float:
    if task.start_time is None:
        raise ValueError(f"task {task.id} has not started")
    return task.start_time - task.submit_time


def calculate_turnaround_time(task: Task) -> float:
    if task.finish_time is None:
        raise ValueError(f"task {task.id} has not finished")
    return task.finish_time - task.submit_time


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def percentile(values: list[float], percentile_value: float) -> float:
    if not 0.0 <= percentile_value <= 1.0:
        raise ValueError("percentile_value must be between 0 and 1")
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile_value * len(ordered)) - 1
    index = max(0, min(index, len(ordered) - 1))
    return ordered[index]


def p95(values: list[float]) -> float:
    return percentile(values, 0.95)


def p99(values: list[float]) -> float:
    return percentile(values, 0.99)


def calculate_worker_utilization(worker: Worker, total_time: float) -> float:
    if total_time <= 0:
        return 0.0
    return worker.total_busy_time / total_time
