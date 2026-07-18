from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.experiments import run_aging_cost, summarize_aging_cost, summarize_by_task_type
from scheduler.strategies import AGING_CONFIG_PRESETS, TOKEN_DOMINANT_WEIGHTS
from scheduler.workloads import build_cost_sensitivity_tasks


def print_summary() -> None:
    tasks = build_cost_sensitivity_tasks()

    print("aging_experiment")
    print("config | avg_wait | max_wait | p95 | p99 | max_queue | utilization")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---:")

    for label, aging_config in AGING_CONFIG_PRESETS.items():
        row = summarize_aging_cost(tasks, label, TOKEN_DOMINANT_WEIGHTS, aging_config)
        print(
            f"{row['strategy']} | "
            f"{row['average_wait_time']:.2f} | "
            f"{row['max_wait_time']:.2f} | "
            f"{row['p95_wait_time']:.2f} | "
            f"{row['p99_wait_time']:.2f} | "
            f"{row['max_ready_queue_length']:.0f} | "
            f"{row['worker_utilization']:.2f}"
        )


def print_task_type_breakdown() -> None:
    tasks = build_cost_sensitivity_tasks()

    print()
    print("task_type_breakdown")

    for label in ["no_aging", "strong_aging"]:
        completed = run_aging_cost(tasks, TOKEN_DOMINANT_WEIGHTS, AGING_CONFIG_PRESETS[label])
        rows = summarize_by_task_type(completed)

        print()
        print(label)
        print("task_type | count | avg_wait | max_wait | p95")
        print("--- | ---: | ---: | ---: | ---:")
        for row in rows:
            print(
                f"{row['task_type']} | "
                f"{row['task_count']:.0f} | "
                f"{row['average_wait_time']:.2f} | "
                f"{row['max_wait_time']:.2f} | "
                f"{row['p95_wait_time']:.2f}"
            )


def main() -> None:
    print_summary()
    print_task_type_breakdown()


if __name__ == "__main__":
    main()

