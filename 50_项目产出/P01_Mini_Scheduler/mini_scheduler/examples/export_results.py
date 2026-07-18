from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.experiments import (
    compare_strategies,
    run_aging_cost,
    run_cost_weights,
    summarize_aging_cost,
    summarize_by_task_type,
    summarize_cost_weights,
    summarize_multi_worker_strategy,
)
from scheduler.strategies import AGING_CONFIG_PRESETS, COST_WEIGHT_PRESETS, TOKEN_DOMINANT_WEIGHTS
from scheduler.workloads import (
    build_cost_sensitivity_tasks,
    build_peak_load_tasks,
    build_prediction_error_tasks,
)


ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
STRATEGIES = ["fifo", "priority", "predicted_sjf", "oracle_sjf", "cost_aware"]
PREDICTION_STRATEGIES = ["fifo", "predicted_sjf", "oracle_sjf"]


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def markdown_table(rows: List[dict]) -> str:
    if not rows:
        return ""

    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_value(row[header]) for header in headers) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, title: str, sections: Iterable[tuple[str, List[dict]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "> Generated reference artifact, not learner-owned work or research evidence.",
        "",
        "The deterministic teaching fixtures use explicit actual durations. In the standard fixtures, estimates equal actual durations, so predicted and oracle SJF are expected to match. The prediction-error counterexample is the only table below that intentionally separates them. Percentiles use the nearest-rank definition.",
        "",
    ]

    for section_title, rows in sections:
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(markdown_table(rows))
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def build_high_load_rows() -> List[dict]:
    return compare_strategies(build_peak_load_tasks(), STRATEGIES)


def build_worker_count_rows() -> List[dict]:
    rows: List[dict] = []
    for strategy_name in STRATEGIES:
        for worker_count in [1, 2, 4, 8]:
            rows.append(summarize_multi_worker_strategy(build_peak_load_tasks(), strategy_name, worker_count))
    return rows


def build_prediction_error_rows() -> List[dict]:
    return compare_strategies(build_prediction_error_tasks(), PREDICTION_STRATEGIES)


def build_cost_weight_rows() -> List[dict]:
    tasks = build_cost_sensitivity_tasks()
    return [
        summarize_cost_weights(tasks, label, weights)
        for label, weights in COST_WEIGHT_PRESETS.items()
    ]


def build_aging_rows() -> List[dict]:
    tasks = build_cost_sensitivity_tasks()
    return [
        summarize_aging_cost(tasks, label, TOKEN_DOMINANT_WEIGHTS, config)
        for label, config in AGING_CONFIG_PRESETS.items()
    ]


def build_task_type_rows() -> List[dict]:
    tasks = build_cost_sensitivity_tasks()
    rows: List[dict] = []
    for label in ["duration_dominant", "token_dominant", "priority_dominant"]:
        completed = run_cost_weights(tasks, COST_WEIGHT_PRESETS[label])
        for row in summarize_by_task_type(completed):
            row = dict(row)
            row["experiment"] = label
            rows.append(row)
    return rows


def build_aging_task_type_rows() -> List[dict]:
    tasks = build_cost_sensitivity_tasks()
    rows: List[dict] = []
    for label in ["no_aging", "strong_aging"]:
        completed = run_aging_cost(tasks, TOKEN_DOMINANT_WEIGHTS, AGING_CONFIG_PRESETS[label])
        for row in summarize_by_task_type(completed):
            row = dict(row)
            row["experiment"] = label
            rows.append(row)
    return rows


def main() -> None:
    high_load_rows = build_high_load_rows()
    worker_count_rows = build_worker_count_rows()
    prediction_error_rows = build_prediction_error_rows()
    cost_weight_rows = build_cost_weight_rows()
    aging_rows = build_aging_rows()
    task_type_rows = build_task_type_rows()
    aging_task_type_rows = build_aging_task_type_rows()

    write_csv(ARTIFACT_DIR / "high_load_summary.csv", high_load_rows)
    write_csv(ARTIFACT_DIR / "worker_count_summary.csv", worker_count_rows)
    write_csv(ARTIFACT_DIR / "prediction_error_summary.csv", prediction_error_rows)
    write_csv(ARTIFACT_DIR / "cost_weight_summary.csv", cost_weight_rows)
    write_csv(ARTIFACT_DIR / "aging_summary.csv", aging_rows)
    write_csv(ARTIFACT_DIR / "task_type_breakdown.csv", task_type_rows)
    write_csv(ARTIFACT_DIR / "aging_task_type_breakdown.csv", aging_task_type_rows)

    write_markdown(
        ARTIFACT_DIR / "experiment_summary_tables.md",
        "Mini Scheduler Experiment Summary Tables",
        [
            ("High Load Strategy Comparison", high_load_rows),
            ("Worker Count Comparison", worker_count_rows),
            ("Prediction Error Counterexample", prediction_error_rows),
            ("Cost Weight Comparison", cost_weight_rows),
            ("Aging Protection Comparison", aging_rows),
            ("Task Type Breakdown", task_type_rows),
            ("Aging Task Type Breakdown", aging_task_type_rows),
        ],
    )

    print(f"exported_results={ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
