from __future__ import annotations

from .models import Task


def build_demo_tasks() -> list[Task]:
    return [
        Task("task-001", "rag_query", 2, 5.0, 0.0, token_count=1200, actual_duration=5.0),
        Task("task-002", "agent_tool", 1, 2.0, 1.0, token_count=500, actual_duration=2.0),
        Task("task-003", "embedding", 3, 1.0, 2.0, token_count=3000, actual_duration=1.0),
        Task("task-004", "long_context", 2, 8.0, 3.0, token_count=8000, actual_duration=8.0),
    ]


def build_low_load_tasks() -> list[Task]:
    tasks: list[Task] = []
    durations = [1.0, 1.5, 2.0, 3.0, 5.0]
    priorities = [2, 2, 1, 3, 2]
    task_types = ["rag_query", "agent_tool", "rag_query", "embedding", "long_context"]

    for index in range(24):
        pattern_index = index % len(durations)
        tasks.append(
            Task(
                id=f"low-{index + 1:03d}",
                task_type=task_types[pattern_index],
                priority=priorities[pattern_index],
                estimated_duration=durations[pattern_index],
                submit_time=index * 4.0,
                token_count=500 + pattern_index * 900,
                actual_duration=durations[pattern_index],
            )
        )

    return tasks


def build_peak_load_tasks() -> list[Task]:
    tasks: list[Task] = []

    for index in range(8):
        tasks.append(
            Task(
                id=f"warmup-{index + 1:03d}",
                task_type="rag_query",
                priority=2,
                estimated_duration=2.0,
                submit_time=index * 2.0,
                token_count=900,
                actual_duration=2.0,
            )
        )

    burst_durations = [1.0, 1.2, 1.5, 2.0, 6.0, 8.0]
    burst_priorities = [1, 2, 2, 3, 2, 3]
    burst_types = ["agent_tool", "rag_query", "embedding", "rag_query", "long_context", "batch_job"]

    for index in range(36):
        pattern_index = index % len(burst_durations)
        tasks.append(
            Task(
                id=f"burst-{index + 1:03d}",
                task_type=burst_types[pattern_index],
                priority=burst_priorities[pattern_index],
                estimated_duration=burst_durations[pattern_index],
                submit_time=20.0 + index * 0.25,
                token_count=600 + pattern_index * 1400,
                actual_duration=burst_durations[pattern_index],
            )
        )

    for index in range(8):
        tasks.append(
            Task(
                id=f"cooldown-{index + 1:03d}",
                task_type="rag_query",
                priority=2,
                estimated_duration=2.5,
                submit_time=40.0 + index * 3.0,
                token_count=1000,
                actual_duration=2.5,
            )
        )

    return tasks


def build_cost_sensitivity_tasks() -> list[Task]:
    tasks: list[Task] = []
    patterns = [
        ("short_high_token", 2, 1.0, 12000),
        ("long_low_token", 2, 8.0, 300),
        ("urgent_medium", 1, 4.0, 2000),
        ("low_priority_short", 3, 1.2, 500),
        ("batch_heavy", 3, 6.0, 9000),
        ("cheap_medium", 2, 3.0, 400),
    ]

    for index in range(30):
        task_type, priority, duration, token_count = patterns[index % len(patterns)]
        tasks.append(
            Task(
                id=f"cost-{index + 1:03d}",
                task_type=task_type,
                priority=priority,
                estimated_duration=duration,
                submit_time=10.0 + index * 0.2,
                token_count=token_count,
                actual_duration=duration,
            )
        )

    return tasks


def build_prediction_error_tasks() -> list[Task]:
    patterns = [
        ("underestimated_long", 1.0, 9.0),
        ("accurate_short", 2.0, 2.0),
        ("overestimated_short", 8.0, 1.0),
        ("accurate_medium", 4.0, 4.0),
    ]
    tasks: list[Task] = []
    for index in range(24):
        task_type, estimate, actual = patterns[index % len(patterns)]
        tasks.append(
            Task(
                id=f"prediction-{index + 1:03d}",
                task_type=task_type,
                priority=2,
                estimated_duration=estimate,
                submit_time=index * 0.1,
                token_count=1_000,
                actual_duration=actual,
            )
        )
    return tasks
