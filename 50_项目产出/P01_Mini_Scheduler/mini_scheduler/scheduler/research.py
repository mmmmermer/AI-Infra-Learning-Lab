from __future__ import annotations

import hashlib
import math
import random
import statistics
from dataclasses import dataclass
from typing import Iterable

from .metrics import average, p95, p99
from .models import Task, Worker
from .simulator import run_multi_worker


TASK_CLASS_PARAMETERS = {
    "short": {"probability": 0.50, "log_mean": math.log(0.5), "log_sigma": 0.35},
    "medium": {"probability": 0.35, "log_mean": math.log(2.0), "log_sigma": 0.40},
    "long": {"probability": 0.15, "log_mean": math.log(8.0), "log_sigma": 0.50},
}


@dataclass(frozen=True)
class ResearchWorkload:
    seed: int
    prediction_error_label: str
    prediction_error_sigma: float
    tasks: tuple[Task, ...]
    phase_by_task_id: dict[str, str]


def _expected_service_time() -> float:
    return sum(
        parameters["probability"]
        * math.exp(parameters["log_mean"] + parameters["log_sigma"] ** 2 / 2.0)
        for parameters in TASK_CLASS_PARAMETERS.values()
    )


def _choose_task_class(value: float) -> str:
    cumulative = 0.0
    for task_class, parameters in TASK_CLASS_PARAMETERS.items():
        cumulative += parameters["probability"]
        if value <= cumulative:
            return task_class
    return "long"


def build_research_workload(
    *,
    seed: int,
    prediction_error_label: str,
    prediction_error_sigma: float,
    worker_count: int = 1,
    target_utilization: float = 0.90,
    warmup_tasks: int = 50,
    measurement_tasks: int = 500,
    cooldown_tasks: int = 50,
) -> ResearchWorkload:
    if worker_count < 1:
        raise ValueError("worker_count must be positive")
    if not 0.0 < target_utilization < 1.0:
        raise ValueError("target_utilization must be between zero and one")
    if min(warmup_tasks, measurement_tasks, cooldown_tasks) < 0 or measurement_tasks == 0:
        raise ValueError("task phase counts must be non-negative and measurement must be positive")
    if prediction_error_sigma < 0.0:
        raise ValueError("prediction_error_sigma must be non-negative")

    workload_rng = random.Random(seed)
    prediction_rng = random.Random(seed + 10_000_019)
    arrival_rate = target_utilization * worker_count / _expected_service_time()
    total_tasks = warmup_tasks + measurement_tasks + cooldown_tasks
    submit_time = 0.0
    tasks: list[Task] = []
    phase_by_task_id: dict[str, str] = {}

    for index in range(total_tasks):
        if index > 0:
            submit_time += workload_rng.expovariate(arrival_rate)

        task_class = _choose_task_class(workload_rng.random())
        parameters = TASK_CLASS_PARAMETERS[task_class]
        actual_duration = workload_rng.lognormvariate(
            parameters["log_mean"], parameters["log_sigma"]
        )
        standard_normal = prediction_rng.gauss(0.0, 1.0)
        multiplier = math.exp(
            prediction_error_sigma * standard_normal - prediction_error_sigma**2 / 2.0
        )
        multiplier = min(4.0, max(0.25, multiplier))
        estimated_duration = max(0.01, actual_duration * multiplier)

        if index < warmup_tasks:
            phase = "warmup"
        elif index < warmup_tasks + measurement_tasks:
            phase = "measurement"
        else:
            phase = "cooldown"

        task_id = f"seed-{seed:03d}-task-{index + 1:04d}"
        phase_by_task_id[task_id] = phase
        tasks.append(
            Task(
                id=task_id,
                task_type=task_class,
                priority={"short": 1, "medium": 2, "long": 3}[task_class],
                estimated_duration=estimated_duration,
                submit_time=submit_time,
                token_count=max(1, round(actual_duration * 500)),
                actual_duration=actual_duration,
            )
        )

    return ResearchWorkload(
        seed=seed,
        prediction_error_label=prediction_error_label,
        prediction_error_sigma=prediction_error_sigma,
        tasks=tuple(tasks),
        phase_by_task_id=phase_by_task_id,
    )


def run_research_strategy(
    workload: ResearchWorkload,
    strategy: str,
    worker_count: int = 1,
) -> list[Task]:
    workers = [Worker(f"worker-{index + 1}") for index in range(worker_count)]
    return run_multi_worker(list(workload.tasks), workers, strategy_name=strategy)


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for original_index, _ in ordered[position:end]:
            ranks[original_index] = average_rank
        position = end
    return ranks


def spearman_rank_correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    left_mean = average(left_ranks)
    right_mean = average(right_ranks)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_ranks, right_ranks, strict=True)
    )
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left_ranks))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right_ranks))
    if left_scale == 0.0 or right_scale == 0.0:
        return 0.0
    return numerator / (left_scale * right_scale)


def task_result_rows(
    workload: ResearchWorkload,
    completed: Iterable[Task],
    strategy: str,
) -> list[dict[str, int | float | str]]:
    rows: list[dict[str, int | float | str]] = []
    for task in completed:
        if task.start_time is None or task.finish_time is None:
            raise ValueError(f"task {task.id} is incomplete")
        wait_time = task.start_time - task.submit_time
        turnaround = task.finish_time - task.submit_time
        rows.append(
            {
                "seed": workload.seed,
                "prediction_error": workload.prediction_error_label,
                "strategy": strategy,
                "task_id": task.id,
                "phase": workload.phase_by_task_id[task.id],
                "task_class": task.task_type,
                "submit_time": task.submit_time,
                "actual_duration": task.service_duration,
                "estimated_duration": task.estimated_duration,
                "start_time": task.start_time,
                "finish_time": task.finish_time,
                "queue_wait": wait_time,
                "turnaround": turnaround,
                "slowdown": turnaround / task.service_duration,
            }
        )
    return rows


def summarize_research_run(
    workload: ResearchWorkload,
    completed: list[Task],
    strategy: str,
    *,
    worker_count: int = 1,
    slo_wait_threshold: float = 10.0,
    long_wait_threshold: float = 30.0,
) -> dict[str, int | float | str]:
    rows = task_result_rows(workload, completed, strategy)
    measurement = [row for row in rows if row["phase"] == "measurement"]
    wait_times = [float(row["queue_wait"]) for row in measurement]
    slowdowns = [float(row["slowdown"]) for row in measurement]
    actual = [float(row["actual_duration"]) for row in measurement]
    estimated = [float(row["estimated_duration"]) for row in measurement]
    absolute_errors = [abs(estimate - duration) for estimate, duration in zip(estimated, actual)]
    first_submit = min(float(row["submit_time"]) for row in measurement)
    last_finish = max(float(row["finish_time"]) for row in measurement)
    all_finish = max(float(row["finish_time"]) for row in rows)
    all_submit = min(float(row["submit_time"]) for row in rows)
    all_service = sum(float(row["actual_duration"]) for row in rows)

    summary: dict[str, int | float | str] = {
        "seed": workload.seed,
        "prediction_error": workload.prediction_error_label,
        "prediction_error_sigma": workload.prediction_error_sigma,
        "strategy": strategy,
        "worker_count": worker_count,
        "measurement_task_count": len(measurement),
        "average_wait_time": average(wait_times),
        "p95_wait_time": p95(wait_times),
        "p99_wait_time": p99(wait_times),
        "max_wait_time": max(wait_times),
        "p95_slowdown": p95(slowdowns),
        "p99_slowdown": p99(slowdowns),
        "slo_violation_rate": sum(value > slo_wait_threshold for value in wait_times)
        / len(wait_times),
        "long_wait_rate": sum(value > long_wait_threshold for value in wait_times)
        / len(wait_times),
        "throughput": len(measurement) / (last_finish - first_submit),
        "worker_utilization": all_service / ((all_finish - all_submit) * worker_count),
        "prediction_mae": average(absolute_errors),
        "prediction_median_absolute_error": statistics.median(absolute_errors),
        "prediction_spearman": spearman_rank_correlation(estimated, actual),
    }

    for task_class in TASK_CLASS_PARAMETERS:
        class_rows = [row for row in measurement if row["task_class"] == task_class]
        class_waits = [float(row["queue_wait"]) for row in class_rows]
        class_slowdowns = [float(row["slowdown"]) for row in class_rows]
        summary[f"{task_class}_task_count"] = len(class_rows)
        summary[f"{task_class}_p95_wait_time"] = p95(class_waits)
        summary[f"{task_class}_p99_wait_time"] = p99(class_waits)
        summary[f"{task_class}_max_wait_time"] = max(class_waits)
        summary[f"{task_class}_p99_slowdown"] = p99(class_slowdowns)

    return summary


def _bootstrap_seed(key: str, bootstrap_seed: int) -> int:
    digest = hashlib.sha256(f"{bootstrap_seed}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def paired_bootstrap(
    strategy_values: list[float],
    baseline_values: list[float],
    *,
    bootstrap_seed: int,
    resamples: int = 5_000,
) -> dict[str, float]:
    if len(strategy_values) != len(baseline_values) or len(strategy_values) < 2:
        raise ValueError("paired bootstrap requires equal lists with at least two seeds")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")

    deltas = [
        strategy - baseline
        for strategy, baseline in zip(strategy_values, baseline_values, strict=True)
    ]
    relative = [
        (strategy - baseline) / baseline if baseline != 0.0 else 0.0
        for strategy, baseline in zip(strategy_values, baseline_values, strict=True)
    ]
    rng = random.Random(bootstrap_seed)
    bootstrap_means: list[float] = []
    bootstrap_medians: list[float] = []
    for _ in range(resamples):
        sample = [deltas[rng.randrange(len(deltas))] for _ in deltas]
        bootstrap_means.append(average(sample))
        bootstrap_medians.append(statistics.median(sample))

    return {
        "mean_delta": average(deltas),
        "median_delta": statistics.median(deltas),
        "mean_relative_change": average(relative),
        "mean_ci_low": _quantile(bootstrap_means, 0.025),
        "mean_ci_high": _quantile(bootstrap_means, 0.975),
        "median_ci_low": _quantile(bootstrap_medians, 0.025),
        "median_ci_high": _quantile(bootstrap_medians, 0.975),
    }


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = math.ceil(probability * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def build_paired_analysis(
    summaries: list[dict[str, int | float | str]],
    *,
    metrics: tuple[str, ...],
    baseline: str = "fifo",
    bootstrap_seed: int = 20260711,
    resamples: int = 5_000,
) -> list[dict[str, int | float | str]]:
    conditions = sorted({str(row["prediction_error"]) for row in summaries})
    strategies = sorted({str(row["strategy"]) for row in summaries if row["strategy"] != baseline})
    output: list[dict[str, int | float | str]] = []

    for condition in conditions:
        condition_rows = [row for row in summaries if row["prediction_error"] == condition]
        baseline_by_seed = {
            int(row["seed"]): row for row in condition_rows if row["strategy"] == baseline
        }
        for strategy in strategies:
            strategy_by_seed = {
                int(row["seed"]): row for row in condition_rows if row["strategy"] == strategy
            }
            seeds = sorted(set(baseline_by_seed) & set(strategy_by_seed))
            for metric in metrics:
                baseline_values = [float(baseline_by_seed[seed][metric]) for seed in seeds]
                strategy_values = [float(strategy_by_seed[seed][metric]) for seed in seeds]
                key = f"{condition}:{strategy}:{metric}"
                result = paired_bootstrap(
                    strategy_values,
                    baseline_values,
                    bootstrap_seed=_bootstrap_seed(key, bootstrap_seed),
                    resamples=resamples,
                )
                output.append(
                    {
                        "prediction_error": condition,
                        "strategy": strategy,
                        "baseline": baseline,
                        "metric": metric,
                        "seed_count": len(seeds),
                        **result,
                    }
                )
    return output
