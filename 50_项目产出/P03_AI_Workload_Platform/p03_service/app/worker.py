from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from time import perf_counter_ns

from .models import TaskRecord
from .rag_workload import execute_rag_retrieval
from .store import InMemoryTaskStore


@dataclass(frozen=True)
class TaskExecution:
    result_json: dict | None
    error_type: str | None
    runtime_ms: float


def execute_task(task: TaskRecord) -> TaskExecution:
    started = perf_counter_ns()
    try:
        sleep_ms = int(task.input_json.get("sleep_ms", 0))
        if not 0 <= sleep_ms <= 5_000:
            raise ValueError("invalid_sleep_ms")
        if sleep_ms:
            sleep(sleep_ms / 1_000)
        if task.input_json.get("force_error"):
            raise ValueError("forced_failure")

        if task.task_type == "rag_retrieval":
            result = execute_rag_retrieval(task)
        else:
            result = {
                "kind": "mock_reference",
                "task_type": task.task_type,
                "echo": task.input_json,
                "quality_status": "not_evaluated",
            }
        return TaskExecution(
            result_json=result,
            error_type=None,
            runtime_ms=(perf_counter_ns() - started) / 1_000_000,
        )
    except (TypeError, ValueError) as error:
        return TaskExecution(
            result_json=None,
            error_type=str(error),
            runtime_ms=(perf_counter_ns() - started) / 1_000_000,
        )


def execute_next(store: InMemoryTaskStore) -> TaskRecord | None:
    task = store.start_next()
    if task is None:
        return None

    execution = execute_task(task)
    if execution.error_type is not None:
        return store.fail(task.task_id, execution.error_type, execution.runtime_ms)
    assert execution.result_json is not None
    return store.succeed(task.task_id, execution.result_json, execution.runtime_ms)
