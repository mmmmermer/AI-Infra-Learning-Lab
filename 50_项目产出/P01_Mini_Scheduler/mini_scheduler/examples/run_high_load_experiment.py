from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Union

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.experiments import compare_strategies
from scheduler.workloads import build_low_load_tasks, build_peak_load_tasks


STRATEGIES = ["fifo", "priority", "sjf", "cost_aware"]
SummaryRow = Dict[str, Union[float, str]]


def print_table(title: str, rows: List[SummaryRow]) -> None:
    print(title)
    print("strategy | avg_wait | max_wait | p95 | p99 | max_queue | utilization")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---:")

    for row in rows:
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


def main() -> None:
    low_load_rows = compare_strategies(build_low_load_tasks(), STRATEGIES)
    peak_load_rows = compare_strategies(build_peak_load_tasks(), STRATEGIES)

    print_table("low_load", low_load_rows)
    print_table("peak_load", peak_load_rows)


if __name__ == "__main__":
    main()
