from __future__ import annotations

from dataclasses import dataclass

from .models import Task


@dataclass(frozen=True)
class CostWeights:
    duration: float
    token: float
    priority: float


@dataclass(frozen=True)
class AgingConfig:
    wait_weight: float
    max_wait_threshold: float
    max_wait_bonus: float
    enforce_max_wait: bool = False


DEFAULT_COST_WEIGHTS = CostWeights(duration=1.0, token=0.001, priority=0.5)
DURATION_DOMINANT_WEIGHTS = CostWeights(duration=1.5, token=0.0005, priority=0.3)
TOKEN_DOMINANT_WEIGHTS = CostWeights(duration=0.7, token=0.003, priority=0.3)
PRIORITY_DOMINANT_WEIGHTS = CostWeights(duration=0.8, token=0.0005, priority=2.0)
DEFAULT_AGING_CONFIG = AgingConfig(wait_weight=0.25, max_wait_threshold=30.0, max_wait_bonus=20.0)


def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.submit_time, task.id))


def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.priority, task.submit_time, task.id))


def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    """Sort by predicted duration.

    The historical ``sjf`` name is kept for the teaching API. It is not an
    oracle policy unless estimates equal actual service times.
    """
    return sorted(tasks, key=lambda task: (task.estimated_duration, task.submit_time, task.id))


def sort_by_predicted_sjf(tasks: list[Task]) -> list[Task]:
    return sort_by_sjf(tasks)


def sort_by_oracle_sjf(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.service_duration, task.submit_time, task.id))


def calculate_cost_score(task: Task, weights: CostWeights = DEFAULT_COST_WEIGHTS) -> float:
    return (
        weights.duration * task.estimated_duration
        + weights.token * task.token_count
        + weights.priority * task.priority
    )


def sort_by_cost_aware(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (calculate_cost_score(task), task.submit_time, task.id))


def sort_by_cost_weights(tasks: list[Task], weights: CostWeights) -> list[Task]:
    return sorted(tasks, key=lambda task: (calculate_cost_score(task, weights), task.submit_time, task.id))


def calculate_aging_cost_score(
    task: Task,
    weights: CostWeights,
    current_time: float,
    aging_config: AgingConfig = DEFAULT_AGING_CONFIG,
) -> float:
    wait_time = max(0.0, current_time - task.submit_time)
    aging_bonus = wait_time * aging_config.wait_weight
    if wait_time >= aging_config.max_wait_threshold:
        aging_bonus += aging_config.max_wait_bonus
    return calculate_cost_score(task, weights) - aging_bonus


def sort_by_aging_cost(
    tasks: list[Task],
    weights: CostWeights,
    current_time: float,
    aging_config: AgingConfig = DEFAULT_AGING_CONFIG,
) -> list[Task]:
    if aging_config.enforce_max_wait:
        overdue_tasks = [
            task for task in tasks if current_time - task.submit_time >= aging_config.max_wait_threshold
        ]
        if overdue_tasks:
            overdue_ids = {task.id for task in overdue_tasks}
            protected = sorted(overdue_tasks, key=lambda task: (task.submit_time, task.id))
            normal = sorted(
                [task for task in tasks if task.id not in overdue_ids],
                key=lambda task: (
                    calculate_aging_cost_score(task, weights, current_time, aging_config),
                    task.submit_time,
                    task.id,
                ),
            )
            return protected + normal

    return sorted(
        tasks,
        key=lambda task: (
            calculate_aging_cost_score(task, weights, current_time, aging_config),
            task.submit_time,
            task.id,
        ),
    )


STRATEGY_SORTERS = {
    "fifo": sort_by_fifo,
    "priority": sort_by_priority,
    "sjf": sort_by_sjf,
    "predicted_sjf": sort_by_predicted_sjf,
    "oracle_sjf": sort_by_oracle_sjf,
    "cost_aware": sort_by_cost_aware,
}


COST_WEIGHT_PRESETS = {
    "default": DEFAULT_COST_WEIGHTS,
    "duration_dominant": DURATION_DOMINANT_WEIGHTS,
    "token_dominant": TOKEN_DOMINANT_WEIGHTS,
    "priority_dominant": PRIORITY_DOMINANT_WEIGHTS,
}


AGING_CONFIG_PRESETS = {
    "no_aging": AgingConfig(wait_weight=0.0, max_wait_threshold=999999.0, max_wait_bonus=0.0),
    "gentle_aging": AgingConfig(wait_weight=0.15, max_wait_threshold=40.0, max_wait_bonus=10.0),
    "strong_aging": AgingConfig(
        wait_weight=0.35,
        max_wait_threshold=25.0,
        max_wait_bonus=25.0,
        enforce_max_wait=True,
    ),
}
