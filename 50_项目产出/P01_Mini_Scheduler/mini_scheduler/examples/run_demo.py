from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.metrics import (
    average,
    calculate_turnaround_time,
    calculate_wait_time,
    calculate_worker_utilization,
    p95,
    p99,
)
from scheduler.models import Worker
from scheduler.simulator import run_single_worker
from scheduler.workloads import build_demo_tasks


STRATEGIES = ("fifo", "priority", "sjf", "cost_aware")


def build_demo_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy_name in STRATEGIES:
        worker = Worker(id=f"worker-{strategy_name}")
        completed = run_single_worker(
            build_demo_tasks(),
            worker,
            strategy_name=strategy_name,
        )
        waits = [calculate_wait_time(task) for task in completed]
        turnarounds = [calculate_turnaround_time(task) for task in completed]
        finish_times = [task.finish_time for task in completed]
        if any(value is None for value in finish_times):
            raise RuntimeError("completed demo task is missing finish_time")
        simulation_end = max(float(value) for value in finish_times)
        rows.append(
            {
                "strategy": strategy_name,
                "order": [task.id for task in completed],
                "average_wait": average(waits),
                "average_turnaround": average(turnarounds),
                "p95_wait": p95(waits),
                "p99_wait": p99(waits),
                "worker_utilization": calculate_worker_utilization(
                    worker,
                    simulation_end,
                ),
            }
        )
    return rows


def main() -> None:
    print("strategy | order | average_wait | average_turnaround | p95 | p99 | utilization")
    for row in build_demo_rows():
        print(
            f"{row['strategy']} | {','.join(row['order'])} | "
            f"{row['average_wait']:.3f} | {row['average_turnaround']:.3f} | "
            f"{row['p95_wait']:.3f} | {row['p99_wait']:.3f} | "
            f"{row['worker_utilization']:.3f}"
        )


if __name__ == "__main__":
    main()
