from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.experiments import run_cost_weights, summarize_by_task_type, summarize_cost_weights
from scheduler.strategies import COST_WEIGHT_PRESETS
from scheduler.workloads import build_cost_sensitivity_tasks


def main() -> None:
    tasks = build_cost_sensitivity_tasks()

    print("cost_weight_experiment")
    print("preset | avg_wait | max_wait | p95 | p99 | max_queue | utilization")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---:")

    for label, weights in COST_WEIGHT_PRESETS.items():
        row = summarize_cost_weights(tasks, label, weights)
        print(
            f"{row['strategy']} | "
            f"{row['average_wait_time']:.2f} | "
            f"{row['max_wait_time']:.2f} | "
            f"{row['p95_wait_time']:.2f} | "
            f"{row['p99_wait_time']:.2f} | "
            f"{row['max_ready_queue_length']:.0f} | "
            f"{row['worker_utilization']:.2f}"
        )

    print()
    print("task_type_breakdown")

    for label in ["duration_dominant", "token_dominant", "priority_dominant"]:
        weights = COST_WEIGHT_PRESETS[label]
        completed = run_cost_weights(tasks, weights)
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


if __name__ == "__main__":
    main()
