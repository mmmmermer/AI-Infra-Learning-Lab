import pytest

from scheduler.research import (
    build_paired_analysis,
    build_research_workload,
    paired_bootstrap,
    run_research_strategy,
    summarize_research_run,
)


def test_common_random_numbers_keep_actual_workload_fixed_across_error_levels():
    exact = build_research_workload(
        seed=17,
        prediction_error_label="exact",
        prediction_error_sigma=0.0,
        warmup_tasks=2,
        measurement_tasks=10,
        cooldown_tasks=2,
    )
    noisy = build_research_workload(
        seed=17,
        prediction_error_label="high",
        prediction_error_sigma=0.8,
        warmup_tasks=2,
        measurement_tasks=10,
        cooldown_tasks=2,
    )

    assert [task.submit_time for task in exact.tasks] == [task.submit_time for task in noisy.tasks]
    assert [task.actual_duration for task in exact.tasks] == [
        task.actual_duration for task in noisy.tasks
    ]
    assert any(
        exact_task.estimated_duration != noisy_task.estimated_duration
        for exact_task, noisy_task in zip(exact.tasks, noisy.tasks, strict=True)
    )


def test_research_workload_phase_counts_and_validation():
    workload = build_research_workload(
        seed=18,
        prediction_error_label="low",
        prediction_error_sigma=0.35,
        warmup_tasks=3,
        measurement_tasks=12,
        cooldown_tasks=4,
    )

    phases = list(workload.phase_by_task_id.values())
    assert phases.count("warmup") == 3
    assert phases.count("measurement") == 12
    assert phases.count("cooldown") == 4
    with pytest.raises(ValueError):
        build_research_workload(
            seed=1,
            prediction_error_label="bad",
            prediction_error_sigma=-0.1,
        )


def test_research_summary_reports_tail_fairness_and_predictor_metrics():
    workload = build_research_workload(
        seed=19,
        prediction_error_label="medium",
        prediction_error_sigma=0.5,
        warmup_tasks=5,
        measurement_tasks=80,
        cooldown_tasks=5,
    )
    completed = run_research_strategy(workload, "predicted_sjf")
    summary = summarize_research_run(workload, completed, "predicted_sjf")

    assert summary["measurement_task_count"] == 80
    assert summary["p99_wait_time"] >= summary["p95_wait_time"]
    assert summary["long_p99_wait_time"] >= 0.0
    assert -1.0 <= summary["prediction_spearman"] <= 1.0


def test_paired_bootstrap_is_deterministic_and_validates_inputs():
    first = paired_bootstrap([8.0, 9.0, 10.0], [10.0, 10.0, 10.0], bootstrap_seed=7, resamples=200)
    second = paired_bootstrap([8.0, 9.0, 10.0], [10.0, 10.0, 10.0], bootstrap_seed=7, resamples=200)

    assert first == second
    assert first["mean_delta"] == pytest.approx(-1.0)
    assert first["mean_ci_low"] <= first["mean_delta"] <= first["mean_ci_high"]
    with pytest.raises(ValueError):
        paired_bootstrap([1.0], [1.0], bootstrap_seed=7)


def test_build_paired_analysis_pairs_rows_by_seed():
    summaries = []
    for seed, fifo, predicted in [(17, 10.0, 8.0), (18, 12.0, 9.0), (19, 11.0, 10.0)]:
        summaries.extend(
            [
                {"seed": seed, "prediction_error": "low", "strategy": "fifo", "p99": fifo},
                {
                    "seed": seed,
                    "prediction_error": "low",
                    "strategy": "predicted_sjf",
                    "p99": predicted,
                },
            ]
        )

    rows = build_paired_analysis(
        summaries,
        metrics=("p99",),
        bootstrap_seed=11,
        resamples=200,
    )

    assert len(rows) == 1
    assert rows[0]["seed_count"] == 3
    assert rows[0]["mean_delta"] < 0.0
