from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.metrics import calculate_wait_time, p95
from scheduler.models import Task, TaskStatus, Worker
from scheduler.simulator import run_multi_worker, run_single_worker
from scheduler.strategies import AGING_CONFIG_PRESETS, COST_WEIGHT_PRESETS, calculate_cost_score, sort_by_cost_aware, sort_by_priority
from scheduler.workloads import build_cost_sensitivity_tasks, build_peak_load_tasks


def main() -> None:
    tasks = [
        Task("a", "rag", 3, 4.0, 0.0, token_count=100),
        Task("b", "rag", 1, 2.0, 1.0, token_count=100),
        Task("c", "rag", 2, 1.0, 2.0, token_count=1000),
    ]

    assert [task.id for task in sort_by_priority(tasks)] == ["b", "c", "a"]
    assert [task.id for task in sort_by_cost_aware(tasks)] == ["b", "c", "a"]
    assert calculate_cost_score(tasks[0]) == 5.6

    completed = run_single_worker(tasks, Worker("w1"), strategy_name="priority")
    wait_times = [calculate_wait_time(task) for task in completed]

    assert [task.status for task in completed] == [
        TaskStatus.SUCCEEDED,
        TaskStatus.SUCCEEDED,
        TaskStatus.SUCCEEDED,
    ]
    assert p95(wait_times) >= 0.0
    assert len(build_peak_load_tasks()) == 52
    assert len(build_cost_sensitivity_tasks()) == 30
    assert "duration_dominant" in COST_WEIGHT_PRESETS
    assert "strong_aging" in AGING_CONFIG_PRESETS
    multi_completed = run_multi_worker(tasks, [Worker("w1"), Worker("w2")], strategy_name="fifo")
    assert len(multi_completed) == len(tasks)

    print("smoke_check=passed")


if __name__ == "__main__":
    main()
