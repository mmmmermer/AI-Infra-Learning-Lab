from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable


@dataclass(frozen=True)
class InferenceProfile:
    fixed_overhead_ms: float = 5.0
    prefill_ms_per_token: float = 0.05
    decode_ms_per_token: float = 2.0

    def __post_init__(self) -> None:
        if min(
            self.fixed_overhead_ms,
            self.prefill_ms_per_token,
            self.decode_ms_per_token,
        ) < 0:
            raise ValueError("profile costs must be non-negative")


@dataclass(frozen=True)
class InferenceTask:
    task_id: str
    request_kind: str
    arrival_ms: float
    prompt_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if not self.task_id or not self.request_kind:
            raise ValueError("task_id and request_kind are required")
        if self.arrival_ms < 0 or self.prompt_tokens < 0 or self.output_tokens < 1:
            raise ValueError("arrival and token counts are outside the supported range")


@dataclass(frozen=True)
class InferenceResult:
    task_id: str
    request_kind: str
    arrival_ms: float
    prompt_tokens: int
    output_tokens: int
    queue_wait_ms: float
    ttft_ms: float
    tpot_ms: float | None
    service_ms: float
    total_latency_ms: float
    finished_at_ms: float


def simulate_fifo(
    tasks: Iterable[InferenceTask],
    profile: InferenceProfile | None = None,
) -> list[InferenceResult]:
    active_profile = profile or InferenceProfile()
    indexed_tasks = list(enumerate(tasks))
    ordered_tasks = sorted(indexed_tasks, key=lambda item: (item[1].arrival_ms, item[0]))
    available_at_ms = 0.0
    results: list[InferenceResult] = []

    for _, task in ordered_tasks:
        started_at_ms = max(task.arrival_ms, available_at_ms)
        queue_wait_ms = started_at_ms - task.arrival_ms
        prefill_ms = task.prompt_tokens * active_profile.prefill_ms_per_token
        decode_ms = task.output_tokens * active_profile.decode_ms_per_token
        service_ms = active_profile.fixed_overhead_ms + prefill_ms + decode_ms
        ttft_ms = (
            queue_wait_ms
            + active_profile.fixed_overhead_ms
            + prefill_ms
            + active_profile.decode_ms_per_token
        )
        total_latency_ms = queue_wait_ms + service_ms
        finished_at_ms = task.arrival_ms + total_latency_ms
        tpot_ms = active_profile.decode_ms_per_token if task.output_tokens > 1 else None
        available_at_ms = finished_at_ms
        results.append(
            InferenceResult(
                task_id=task.task_id,
                request_kind=task.request_kind,
                arrival_ms=task.arrival_ms,
                prompt_tokens=task.prompt_tokens,
                output_tokens=task.output_tokens,
                queue_wait_ms=queue_wait_ms,
                ttft_ms=ttft_ms,
                tpot_ms=tpot_ms,
                service_ms=service_ms,
                total_latency_ms=total_latency_ms,
                finished_at_ms=finished_at_ms,
            )
        )

    return results


def nearest_rank_percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("at least one value is required")
    if not 0 < probability <= 1:
        raise ValueError("probability must be in (0, 1]")
    rank = ceil(probability * len(ordered))
    return ordered[rank - 1]


def summarize(results: Iterable[InferenceResult]) -> dict[str, float | int]:
    rows = list(results)
    if not rows:
        raise ValueError("at least one result is required")
    elapsed_ms = max(row.finished_at_ms for row in rows) - min(
        row.arrival_ms for row in rows
    )
    output_tokens = sum(row.output_tokens for row in rows)
    return {
        "request_count": len(rows),
        "output_tokens": output_tokens,
        "p95_queue_wait_ms": nearest_rank_percentile(
            (row.queue_wait_ms for row in rows), 0.95
        ),
        "p99_queue_wait_ms": nearest_rank_percentile(
            (row.queue_wait_ms for row in rows), 0.99
        ),
        "p95_ttft_ms": nearest_rank_percentile((row.ttft_ms for row in rows), 0.95),
        "p99_ttft_ms": nearest_rank_percentile((row.ttft_ms for row in rows), 0.99),
        "p95_total_latency_ms": nearest_rank_percentile(
            (row.total_latency_ms for row in rows), 0.95
        ),
        "p99_total_latency_ms": nearest_rank_percentile(
            (row.total_latency_ms for row in rows), 0.99
        ),
        "aggregate_output_tokens_per_second": (
            output_tokens * 1000 / elapsed_ms if elapsed_ms > 0 else 0.0
        ),
    }


def summarize_by_kind(
    results: Iterable[InferenceResult],
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[InferenceResult]] = {}
    for result in results:
        groups.setdefault(result.request_kind, []).append(result)
    if not groups:
        raise ValueError("at least one result is required")
    summaries: dict[str, dict[str, float | int]] = {}
    for kind, rows in sorted(groups.items()):
        metrics = summarize(rows)
        metrics.pop("aggregate_output_tokens_per_second")
        summaries[kind] = metrics
    return summaries
