from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.experiments import summarize_multi_worker_strategy
from scheduler.workloads import build_peak_load_tasks


def main() -> None:
    tasks = build_peak_load_tasks()
    worker_counts = [1, 2, 4, 8]
    strategies = ["fifo", "priority", "sjf", "cost_aware"]

    print("worker_count_experiment")
    print("strategy | workers | avg_wait | max_wait | p95 | p99 | max_queue | utilization")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---:")

    for strategy_name in strategies:
        for worker_count in worker_counts:
            row = summarize_multi_worker_strategy(tasks, strategy_name, worker_count)
            print(
                f"{row['strategy']} | "
                f"{row['worker_count']:.0f} | "
                f"{row['average_wait_time']:.2f} | "
                f"{row['max_wait_time']:.2f} | "
                f"{row['p95_wait_time']:.2f} | "
                f"{row['p99_wait_time']:.2f} | "
                f"{row['max_ready_queue_length']:.0f} | "
                f"{row['worker_utilization']:.2f}"
            )


if __name__ == "__main__":
    main()

