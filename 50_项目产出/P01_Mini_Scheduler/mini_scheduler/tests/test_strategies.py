from scheduler.models import Task
from scheduler.strategies import (
    AgingConfig,
    CostWeights,
    calculate_aging_cost_score,
    calculate_cost_score,
    sort_by_cost_weights,
    sort_by_cost_aware,
    sort_by_fifo,
    sort_by_oracle_sjf,
    sort_by_predicted_sjf,
    sort_by_priority,
    sort_by_sjf,
)


def test_sort_by_fifo():
    tasks = [
        Task("b", "rag", 2, 1.0, 2.0),
        Task("a", "rag", 1, 1.0, 1.0),
        Task("c", "rag", 3, 1.0, 3.0),
    ]

    assert [task.id for task in sort_by_fifo(tasks)] == ["a", "b", "c"]


def test_sort_by_priority():
    tasks = [
        Task("a", "rag", 3, 1.0, 0.0),
        Task("b", "rag", 1, 1.0, 0.0),
        Task("c", "rag", 2, 1.0, 0.0),
    ]

    assert [task.id for task in sort_by_priority(tasks)] == ["b", "c", "a"]


def test_sort_by_sjf():
    tasks = [
        Task("a", "rag", 1, 5.0, 0.0),
        Task("b", "rag", 1, 2.0, 0.0),
        Task("c", "rag", 1, 3.0, 0.0),
    ]

    assert [task.id for task in sort_by_sjf(tasks)] == ["b", "c", "a"]


def test_predicted_and_oracle_sjf_use_different_durations():
    tasks = [
        Task("underestimated", "rag", 1, 1.0, 0.0, actual_duration=9.0),
        Task("accurate", "rag", 1, 3.0, 0.0, actual_duration=3.0),
    ]

    assert [task.id for task in sort_by_predicted_sjf(tasks)] == ["underestimated", "accurate"]
    assert [task.id for task in sort_by_oracle_sjf(tasks)] == ["accurate", "underestimated"]


def test_sort_by_cost_aware():
    tasks = [
        Task("a", "rag", 1, 4.0, 0.0, token_count=100),
        Task("b", "rag", 2, 2.0, 0.0, token_count=100),
        Task("c", "rag", 1, 2.0, 0.0, token_count=500),
    ]

    assert [task.id for task in sort_by_cost_aware(tasks)] == ["c", "b", "a"]


def test_calculate_cost_score():
    task = Task("a", "rag", 2, 3.0, 0.0, token_count=1000)

    assert calculate_cost_score(task) == 5.0


def test_sort_by_cost_weights():
    tasks = [
        Task("short", "rag", 3, 1.0, 0.0, token_count=5000),
        Task("cheap", "rag", 2, 2.0, 0.0, token_count=300),
    ]
    weights = CostWeights(duration=1.0, token=0.01, priority=0.0)

    assert [task.id for task in sort_by_cost_weights(tasks, weights)] == ["cheap", "short"]


def test_calculate_aging_cost_score_reduces_score_as_wait_increases():
    task = Task("a", "rag", 2, 4.0, 0.0, token_count=1000)
    weights = CostWeights(duration=1.0, token=0.001, priority=0.5)
    aging_config = AgingConfig(wait_weight=0.5, max_wait_threshold=10.0, max_wait_bonus=5.0)

    early_score = calculate_aging_cost_score(task, weights, current_time=2.0, aging_config=aging_config)
    late_score = calculate_aging_cost_score(task, weights, current_time=12.0, aging_config=aging_config)

    assert late_score < early_score
