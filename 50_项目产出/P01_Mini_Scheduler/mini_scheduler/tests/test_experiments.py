from scheduler.experiments import calculate_ready_queue_lengths, run_aging_cost, summarize_by_task_type, summarize_strategy
from scheduler.models import Task, TaskStatus
from scheduler.strategies import AGING_CONFIG_PRESETS, TOKEN_DOMINANT_WEIGHTS
from scheduler.workloads import (
    build_cost_sensitivity_tasks,
    build_peak_load_tasks,
    build_prediction_error_tasks,
)


def test_calculate_ready_queue_lengths():
    tasks = [
        Task("a", "rag", 1, 1.0, 0.0, start_time=0.0, finish_time=1.0),
        Task("b", "rag", 1, 1.0, 0.0, start_time=1.0, finish_time=2.0),
        Task("c", "rag", 1, 1.0, 0.0, start_time=2.0, finish_time=3.0),
    ]

    assert calculate_ready_queue_lengths(tasks) == [2, 1, 0]


def test_summarize_strategy_peak_load():
    summary = summarize_strategy(build_peak_load_tasks(), "fifo")

    assert summary["task_count"] == 52.0
    assert summary["p95_wait_time"] >= summary["average_wait_time"]
    assert summary["max_ready_queue_length"] > 1.0


def test_cost_sensitivity_workload():
    tasks = build_cost_sensitivity_tasks()

    assert len(tasks) == 30
    assert {task.task_type for task in tasks} >= {"short_high_token", "long_low_token", "urgent_medium"}


def test_summarize_by_task_type():
    tasks = [
        Task("a", "rag", 1, 1.0, 0.0, start_time=1.0, finish_time=2.0),
        Task("b", "rag", 1, 1.0, 0.0, start_time=3.0, finish_time=4.0),
        Task("c", "batch", 1, 1.0, 0.0, start_time=5.0, finish_time=6.0),
    ]

    rows = summarize_by_task_type(tasks)

    assert rows[0]["task_type"] == "batch"
    assert rows[0]["average_wait_time"] == 5.0
    assert rows[1]["task_type"] == "rag"
    assert rows[1]["average_wait_time"] == 2.0


def test_run_aging_cost_completes_tasks():
    completed = run_aging_cost(
        build_cost_sensitivity_tasks(),
        TOKEN_DOMINANT_WEIGHTS,
        AGING_CONFIG_PRESETS["strong_aging"],
    )

    assert len(completed) == 30
    assert all(task.status == TaskStatus.SUCCEEDED for task in completed)


def test_prediction_error_workload_separates_estimate_from_actual_duration():
    tasks = build_prediction_error_tasks()

    assert len(tasks) == 24
    assert any(task.estimated_duration < task.service_duration for task in tasks)
    assert any(task.estimated_duration > task.service_duration for task in tasks)
