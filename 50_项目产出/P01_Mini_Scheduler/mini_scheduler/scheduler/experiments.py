from __future__ import annotations

from typing import Dict, List, Union

from .metrics import (
    average,
    calculate_turnaround_time,
    calculate_wait_time,
    calculate_worker_utilization,
    p95,
    p99,
)
from .models import Task, Worker
from .simulator import run_multi_worker, run_single_worker
from .strategies import AgingConfig, CostWeights, sort_by_aging_cost, sort_by_cost_weights


def calculate_ready_queue_lengths(completed_tasks: list[Task]) -> list[int]:
    lengths: list[int] = []

    for current_task in completed_tasks:
        if current_task.start_time is None:
            continue
        current_time = current_task.start_time
        ready_count = 0

        for task in completed_tasks:
            if task.start_time is None:
                continue
            # A task that starts at current_time has left the ready queue.
            if task.submit_time <= current_time and task.start_time > current_time:
                ready_count += 1

        lengths.append(ready_count)

    return lengths


SummaryValue = Union[float, str]
SummaryRow = Dict[str, SummaryValue]


def _summarize_completed_tasks(
    completed: List[Task],
    worker: Worker,
    label: str,
    worker_count: int = 1,
) -> SummaryRow:
    wait_times = [calculate_wait_time(task) for task in completed]
    turnaround_times = [calculate_turnaround_time(task) for task in completed]
    queue_lengths = calculate_ready_queue_lengths(completed)
    total_time = max((task.finish_time or 0.0) for task in completed) if completed else 0.0
    utilization_denominator = total_time * worker_count

    return {
        "strategy": label,
        "task_count": float(len(completed)),
        "average_wait_time": average(wait_times),
        "max_wait_time": max(wait_times) if wait_times else 0.0,
        "p95_wait_time": p95(wait_times),
        "p99_wait_time": p99(wait_times),
        "average_turnaround_time": average(turnaround_times),
        "max_ready_queue_length": float(max(queue_lengths) if queue_lengths else 0),
        "worker_utilization": calculate_worker_utilization(worker, utilization_denominator),
    }


def summarize_workers(completed: List[Task], workers: List[Worker], label: str) -> SummaryRow:
    combined_worker = Worker("combined", total_busy_time=sum(worker.total_busy_time for worker in workers))
    return _summarize_completed_tasks(completed, combined_worker, label, worker_count=len(workers))


def summarize_strategy(tasks: list[Task], strategy_name: str) -> SummaryRow:
    worker = Worker("worker-1")
    completed = run_single_worker(tasks, worker, strategy_name=strategy_name)
    return _summarize_completed_tasks(completed, worker, strategy_name)


def compare_strategies(tasks: list[Task], strategy_names: list[str]) -> List[SummaryRow]:
    return [summarize_strategy(tasks, strategy_name) for strategy_name in strategy_names]


def summarize_cost_weights(tasks: list[Task], label: str, weights: CostWeights) -> SummaryRow:
    worker = Worker("worker-1")
    completed = run_single_worker(
        tasks,
        worker,
        selector=lambda available_tasks, current_time: sort_by_cost_weights(available_tasks, weights)[0],
    )
    return _summarize_completed_tasks(completed, worker, label)


def run_cost_weights(tasks: list[Task], weights: CostWeights) -> List[Task]:
    worker = Worker("worker-1")
    return run_single_worker(
        tasks,
        worker,
        selector=lambda available_tasks, current_time: sort_by_cost_weights(available_tasks, weights)[0],
    )


def summarize_by_task_type(completed: List[Task]) -> List[SummaryRow]:
    groups: Dict[str, List[Task]] = {}

    for task in completed:
        groups.setdefault(task.task_type, []).append(task)

    rows: List[SummaryRow] = []
    for task_type in sorted(groups):
        tasks = groups[task_type]
        wait_times = [calculate_wait_time(task) for task in tasks]
        turnaround_times = [calculate_turnaround_time(task) for task in tasks]

        rows.append(
            {
                "task_type": task_type,
                "task_count": float(len(tasks)),
                "average_wait_time": average(wait_times),
                "max_wait_time": max(wait_times) if wait_times else 0.0,
                "p95_wait_time": p95(wait_times),
                "average_turnaround_time": average(turnaround_times),
            }
        )

    return rows


def run_aging_cost(tasks: list[Task], weights: CostWeights, aging_config: AgingConfig) -> List[Task]:
    worker = Worker("worker-1")
    return run_single_worker(
        tasks,
        worker,
        selector=lambda available_tasks, current_time: sort_by_aging_cost(
            available_tasks,
            weights,
            current_time,
            aging_config,
        )[0],
    )


def summarize_aging_cost(
    tasks: list[Task],
    label: str,
    weights: CostWeights,
    aging_config: AgingConfig,
) -> SummaryRow:
    completed = run_aging_cost(tasks, weights, aging_config)
    worker = Worker("worker-1", total_busy_time=sum(task.service_duration for task in completed))
    total_time = max((task.finish_time or 0.0) for task in completed) if completed else 0.0
    worker.available_at = total_time
    return _summarize_completed_tasks(completed, worker, label)


def summarize_multi_worker_strategy(
    tasks: list[Task],
    strategy_name: str,
    worker_count: int,
) -> SummaryRow:
    workers = [Worker(f"worker-{index + 1}") for index in range(worker_count)]
    completed = run_multi_worker(tasks, workers, strategy_name=strategy_name)
    row = summarize_workers(completed, workers, strategy_name)
    row["worker_count"] = float(worker_count)
    return row
