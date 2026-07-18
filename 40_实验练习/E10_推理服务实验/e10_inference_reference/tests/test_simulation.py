import pytest

from e10_reference import (
    InferenceProfile,
    InferenceTask,
    nearest_rank_percentile,
    simulate_fifo,
    summarize,
    summarize_by_kind,
)


def make_task(task_id: str, arrival_ms: float, prompt: int, output: int):
    return InferenceTask(task_id, "test", arrival_ms, prompt, output)


def test_service_ttft_and_tpot_are_separate_metrics():
    profile = InferenceProfile(10.0, 0.5, 20.0)
    result = simulate_fifo([make_task("one", 0, 100, 3)], profile)[0]

    assert result.service_ms == 120.0
    assert result.ttft_ms == 80.0
    assert result.tpot_ms == 20.0
    assert result.total_latency_ms == 120.0


def test_fifo_queue_wait_uses_previous_finish_time():
    profile = InferenceProfile(0.0, 0.0, 10.0)
    results = simulate_fifo(
        [make_task("first", 0, 0, 2), make_task("second", 5, 0, 1)], profile
    )

    assert results[0].queue_wait_ms == 0.0
    assert results[1].queue_wait_ms == 15.0
    assert results[1].total_latency_ms == 25.0


def test_nearest_rank_percentile_is_explicit_and_deterministic():
    values = list(range(1, 101))

    assert nearest_rank_percentile(values, 0.95) == 95
    assert nearest_rank_percentile(values, 0.99) == 99


def test_single_output_token_has_no_tpot_sample():
    result = simulate_fifo([make_task("one", 0, 10, 1)])[0]

    assert result.tpot_ms is None


def test_summary_reports_tail_latency_and_aggregate_throughput():
    results = simulate_fifo(
        [make_task(f"task-{index}", index * 100, 100, 10) for index in range(20)]
    )
    metrics = summarize(results)

    assert metrics["request_count"] == 20
    assert metrics["p99_total_latency_ms"] >= metrics["p95_total_latency_ms"]
    assert metrics["aggregate_output_tokens_per_second"] > 0


def test_invalid_workload_is_rejected():
    with pytest.raises(ValueError):
        make_task("bad", 0, 10, 0)


def test_summary_can_be_grouped_without_mixing_request_kinds():
    results = simulate_fifo(
        [
            InferenceTask("short", "short_chat", 0, 100, 10),
            InferenceTask("long", "long_report", 1_000, 1_000, 100),
        ]
    )
    grouped = summarize_by_kind(results)

    assert grouped["short_chat"]["request_count"] == 1
    assert "aggregate_output_tokens_per_second" not in grouped["short_chat"]
    assert grouped["long_report"]["p95_total_latency_ms"] > grouped["short_chat"][
        "p95_total_latency_ms"
    ]
