from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from scheduler.research import (
    build_paired_analysis,
    build_research_workload,
    run_research_strategy,
    summarize_research_run,
    task_result_rows,
)


PREDICTION_ERROR_LEVELS = {"exact": 0.0, "low": 0.35, "high": 0.80}
STRATEGIES = ("fifo", "predicted_sjf", "oracle_sjf")
PAIRED_METRICS = (
    "average_wait_time",
    "p95_wait_time",
    "p99_wait_time",
    "p99_slowdown",
    "slo_violation_rate",
    "long_p99_wait_time",
    "long_p99_slowdown",
)


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[4]
    default_output = (
        repository_root
        / "60_科研训练"
        / "研究项目"
        / "RQ01_RAG_Agent请求调度尾延迟"
        / "artifacts"
        / "rq01_e2_pilot_20260711"
    )
    parser = argparse.ArgumentParser(description="Run the preregistered RQ01 E2 synthetic pilot")
    parser.add_argument("--output-dir", type=Path, default=default_output)
    parser.add_argument("--seed-start", type=int, default=17)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument("--warmup-tasks", type=int, default=50)
    parser.add_argument("--measurement-tasks", type=int, default=500)
    parser.add_argument("--cooldown-tasks", type=int, default=50)
    parser.add_argument("--target-utilization", type=float, default=0.90)
    parser.add_argument("--worker-count", type=int, default=1)
    parser.add_argument("--bootstrap-resamples", type=int, default=5_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260711)
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        if not rows:
            raise ValueError(f"cannot infer CSV fields for empty rows: {path}")
        fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(repository_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def main() -> int:
    args = parse_args()
    if args.seed_count < 2:
        raise ValueError("seed-count must be at least two for paired inference")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repository_root = Path(__file__).resolve().parents[4]
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))
    config = {
        "run_group_id": output_dir.name,
        "phase": "E2 synthetic pilot",
        "evidence_boundary": "synthetic non-preemptive simulation; not P03/RAG/Agent evidence",
        "seeds": seeds,
        "prediction_error_levels": PREDICTION_ERROR_LEVELS,
        "prediction_model": "mean-one lognormal multiplier clipped to [0.25, 4.0]",
        "strategies": STRATEGIES,
        "baseline": "fifo",
        "worker_count": args.worker_count,
        "target_utilization": args.target_utilization,
        "arrival_model": "open-loop exponential interarrival times",
        "service_model": "fixed short/medium/long mixture of lognormal distributions",
        "task_mix": {"short": 0.50, "medium": 0.35, "long": 0.15},
        "warmup_tasks": args.warmup_tasks,
        "measurement_tasks": args.measurement_tasks,
        "cooldown_tasks": args.cooldown_tasks,
        "percentile_method": "nearest-rank within run; seed is inference unit",
        "slo_wait_threshold": 10.0,
        "long_wait_threshold": 30.0,
        "paired_metrics": PAIRED_METRICS,
        "bootstrap_method": "paired seed-level percentile bootstrap",
        "bootstrap_resamples": args.bootstrap_resamples,
        "bootstrap_seed": args.bootstrap_seed,
        "exclusion_rule": "retain every generated seed; write failures to errors.csv",
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    workload_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for error_label, error_sigma in PREDICTION_ERROR_LEVELS.items():
        for seed in seeds:
            try:
                workload = build_research_workload(
                    seed=seed,
                    prediction_error_label=error_label,
                    prediction_error_sigma=error_sigma,
                    worker_count=args.worker_count,
                    target_utilization=args.target_utilization,
                    warmup_tasks=args.warmup_tasks,
                    measurement_tasks=args.measurement_tasks,
                    cooldown_tasks=args.cooldown_tasks,
                )
                for task in workload.tasks:
                    workload_rows.append(
                        {
                            "seed": seed,
                            "prediction_error": error_label,
                            "prediction_error_sigma": error_sigma,
                            "task_id": task.id,
                            "phase": workload.phase_by_task_id[task.id],
                            "task_class": task.task_type,
                            "submit_time": task.submit_time,
                            "actual_duration": task.service_duration,
                            "estimated_duration": task.estimated_duration,
                            "priority": task.priority,
                            "token_count": task.token_count,
                        }
                    )

                for strategy in STRATEGIES:
                    completed = run_research_strategy(workload, strategy, args.worker_count)
                    result_rows.extend(task_result_rows(workload, completed, strategy))
                    summaries.append(
                        summarize_research_run(
                            workload,
                            completed,
                            strategy,
                            worker_count=args.worker_count,
                            slo_wait_threshold=10.0,
                            long_wait_threshold=30.0,
                        )
                    )
            except Exception as exc:
                errors.append(
                    {
                        "seed": seed,
                        "prediction_error": error_label,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "included_in_primary_analysis": False,
                    }
                )

    if errors:
        write_csv(
            output_dir / "errors.csv",
            errors,
            [
                "seed",
                "prediction_error",
                "error_type",
                "message",
                "included_in_primary_analysis",
            ],
        )
        raise RuntimeError(f"pilot contained {len(errors)} failed condition/seed runs")

    paired_rows = build_paired_analysis(
        summaries,
        metrics=PAIRED_METRICS,
        baseline="fifo",
        bootstrap_seed=args.bootstrap_seed,
        resamples=args.bootstrap_resamples,
    )
    write_csv(output_dir / "workload.csv", workload_rows)
    write_csv(output_dir / "per_task_results.csv", result_rows)
    write_csv(output_dir / "per_seed_summary.csv", summaries)
    write_csv(output_dir / "paired_analysis.csv", paired_rows)
    write_csv(
        output_dir / "errors.csv",
        [],
        [
            "seed",
            "prediction_error",
            "error_type",
            "message",
            "included_in_primary_analysis",
        ],
    )

    git_commit = git_value(repository_root, "rev-parse", "HEAD")
    git_dirty = bool(git_value(repository_root, "status", "--porcelain"))
    lock_path = Path(__file__).resolve().parents[1] / "requirements-dev.lock"
    environment = {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "git_commit": git_commit,
        "git_worktree_dirty": git_dirty,
        "dependency_lock": str(lock_path.relative_to(repository_root)),
        "dependency_lock_sha256": sha256_file(lock_path),
    }
    (output_dir / "environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "git_commit.txt").write_text(git_commit + "\n", encoding="ascii")

    summary = {
        "status": "valid E2 synthetic pilot reference; no P03 or scenario conclusion",
        "condition_seed_runs": len(PREDICTION_ERROR_LEVELS) * len(seeds),
        "strategy_runs": len(summaries),
        "workload_rows": len(workload_rows),
        "per_task_result_rows": len(result_rows),
        "failed_runs": 0,
        "paired_analysis": paired_rows,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    stdout_lines = [
        f"run_group_id={output_dir.name}",
        f"condition_seed_runs={summary['condition_seed_runs']}",
        f"strategy_runs={summary['strategy_runs']}",
        f"workload_rows={summary['workload_rows']}",
        f"per_task_result_rows={summary['per_task_result_rows']}",
        "failed_runs=0",
        "boundary=E2 synthetic pilot only; no P03/RAG/Agent conclusion",
    ]
    (output_dir / "stdout.log").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")

    checksum_targets = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "checksums.sha256"
    )
    checksum_lines = [f"{sha256_file(path)}  {path.name}" for path in checksum_targets]
    (output_dir / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="ascii"
    )

    print("\n".join(stdout_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
