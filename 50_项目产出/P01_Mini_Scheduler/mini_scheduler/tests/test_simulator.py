from scheduler.models import Task, TaskStatus, Worker
from scheduler.simulator import run_multi_worker, run_single_worker


def test_run_single_worker_fifo():
    tasks = [
        Task("a", "rag", 2, 3.0, 0.0),
        Task("b", "rag", 1, 1.0, 1.0),
        Task("c", "rag", 3, 2.0, 2.0),
    ]

    worker = Worker("w1")
    completed = run_single_worker(tasks, worker, strategy_name="fifo")

    assert [task.id for task in completed] == ["a", "b", "c"]
    assert [task.start_time for task in completed] == [0.0, 3.0, 4.0]
    assert [task.finish_time for task in completed] == [3.0, 4.0, 6.0]
    assert all(task.status == TaskStatus.SUCCEEDED for task in completed)


def test_simulator_executes_actual_duration_not_estimate():
    tasks = [Task("a", "rag", 1, 1.0, 0.0, actual_duration=4.0)]

    completed = run_single_worker(tasks, Worker("w1"), strategy_name="predicted_sjf")

    assert completed[0].finish_time == 4.0


def test_run_single_worker_priority_waits_for_arrival():
    tasks = [
        Task("slow", "rag", 2, 5.0, 0.0),
        Task("urgent", "rag", 1, 1.0, 4.0),
    ]

    worker = Worker("w1")
    completed = run_single_worker(tasks, worker, strategy_name="priority")

    assert [task.id for task in completed] == ["slow", "urgent"]
    assert completed[1].start_time == 5.0


def test_run_multi_worker_assigns_parallel_tasks():
    tasks = [
        Task("a", "rag", 1, 5.0, 0.0),
        Task("b", "rag", 1, 5.0, 0.0),
        Task("c", "rag", 1, 1.0, 1.0),
    ]

    workers = [Worker("w1"), Worker("w2")]
    completed = run_multi_worker(tasks, workers, strategy_name="fifo")

    assert len(completed) == 3
    assert [task.start_time for task in completed[:2]] == [0.0, 0.0]
    assert completed[2].start_time == 5.0
