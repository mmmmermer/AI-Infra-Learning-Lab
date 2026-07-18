from __future__ import annotations

from dataclasses import replace
from typing import Callable, List, Optional

from .models import Task, TaskStatus, Worker
from .strategies import STRATEGY_SORTERS


TaskSelector = Callable[[List[Task], float], Task]


def _choose_next_task(available_tasks: list[Task], strategy_name: str) -> Task:
    sorter = STRATEGY_SORTERS.get(strategy_name)
    if sorter is None:
        raise ValueError(f"unknown strategy: {strategy_name}")
    return sorter(available_tasks)[0]


def run_single_worker(
    tasks: list[Task],
    worker: Worker,
    strategy_name: str = "fifo",
    selector: Optional[TaskSelector] = None,
) -> list[Task]:
    pending = [replace(task) for task in tasks]
    completed: list[Task] = []
    current_time = worker.available_at

    while pending:
        available_tasks = [task for task in pending if task.submit_time <= current_time]
        if not available_tasks:
            current_time = min(task.submit_time for task in pending)
            available_tasks = [task for task in pending if task.submit_time <= current_time]

        if selector is None:
            next_task = _choose_next_task(available_tasks, strategy_name)
        else:
            next_task = selector(available_tasks, current_time)
        start_time = max(current_time, next_task.submit_time)
        finish_time = start_time + next_task.service_duration

        next_task.start_time = start_time
        next_task.finish_time = finish_time
        next_task.status = TaskStatus.RUNNING

        worker.current_task_id = next_task.id
        worker.available_at = finish_time
        worker.total_busy_time += next_task.service_duration
        current_time = finish_time
        worker.current_task_id = None
        next_task.status = TaskStatus.SUCCEEDED

        completed.append(next_task)
        pending.remove(next_task)

    return completed


def run_multi_worker(
    tasks: list[Task],
    workers: List[Worker],
    strategy_name: str = "fifo",
    selector: Optional[TaskSelector] = None,
) -> list[Task]:
    if not workers:
        raise ValueError("workers must not be empty")

    pending = [replace(task) for task in tasks]
    completed: list[Task] = []

    while pending:
        worker = min(workers, key=lambda item: (item.available_at, item.id))
        current_time = worker.available_at
        available_tasks = [task for task in pending if task.submit_time <= current_time]

        if not available_tasks:
            next_submit_time = min(task.submit_time for task in pending)
            current_time = max(current_time, next_submit_time)
            worker.available_at = current_time
            available_tasks = [task for task in pending if task.submit_time <= current_time]

        if selector is None:
            next_task = _choose_next_task(available_tasks, strategy_name)
        else:
            next_task = selector(available_tasks, current_time)

        start_time = max(current_time, next_task.submit_time)
        finish_time = start_time + next_task.service_duration

        next_task.start_time = start_time
        next_task.finish_time = finish_time
        next_task.status = TaskStatus.RUNNING

        worker.current_task_id = next_task.id
        worker.available_at = finish_time
        worker.total_busy_time += next_task.service_duration
        worker.current_task_id = None
        next_task.status = TaskStatus.SUCCEEDED

        completed.append(next_task)
        pending.remove(next_task)

    return sorted(completed, key=lambda task: (task.start_time or 0.0, task.finish_time or 0.0, task.id))
