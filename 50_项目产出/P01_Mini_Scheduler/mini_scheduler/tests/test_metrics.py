from scheduler.metrics import (
    average,
    calculate_turnaround_time,
    calculate_wait_time,
    calculate_worker_utilization,
    p95,
    p99,
)
from scheduler.models import Task, Worker
import pytest


def test_wait_and_turnaround_time():
    task = Task("a", "rag", 1, 3.0, submit_time=2.0, start_time=5.0, finish_time=8.0)

    assert calculate_wait_time(task) == 3.0
    assert calculate_turnaround_time(task) == 6.0


def test_average_and_percentile():
    values = [1.0, 2.0, 3.0, 4.0]

    assert average(values) == 2.5
    assert p95(values) == 4.0
    assert p99(values) == 4.0


def test_worker_utilization():
    worker = Worker("w1", total_busy_time=6.0)

    assert calculate_worker_utilization(worker, 8.0) == 0.75


def test_percentile_rejects_invalid_probability():
    from scheduler.metrics import percentile

    with pytest.raises(ValueError):
        percentile([1.0], 1.01)
