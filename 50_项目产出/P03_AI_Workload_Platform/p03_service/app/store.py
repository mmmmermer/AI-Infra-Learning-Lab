from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from .auth import Principal
from .metrics import TaskMetricsSnapshot, linear_percentile
from .models import TaskCreate, TaskRecord, TaskStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._queue: deque[str] = deque()
        self._lock = RLock()

    def submit(self, payload: TaskCreate, principal: Principal) -> tuple[TaskRecord, bool]:
        with self._lock:
            idempotency_scope = (
                principal.tenant_id,
                principal.user_id,
                payload.idempotency_key,
            )
            existing_id = self._idempotency.get(idempotency_scope)
            if existing_id is not None:
                return self._copy(self._tasks[existing_id]), False

            now = utc_now()
            task = TaskRecord(
                task_id=str(uuid4()),
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                allowed_permission_groups=principal.allowed_permission_groups,
                task_type=payload.task_type,
                priority=payload.priority,
                estimated_duration_ms=payload.estimated_duration_ms,
                idempotency_key=payload.idempotency_key,
                input_json=payload.input_json,
                status=TaskStatus.QUEUED,
                created_at=now,
                queued_at=now,
            )
            self._tasks[task.task_id] = task
            self._idempotency[idempotency_scope] = task.task_id
            self._queue.append(task.task_id)
            return self._copy(task), True

    def get(
        self,
        task_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None and (
                (tenant_id is not None and task.tenant_id != tenant_id)
                or (user_id is not None and task.user_id != user_id)
            ):
                return None
            return self._copy(task) if task is not None else None

    def start_next(self) -> TaskRecord | None:
        with self._lock:
            if not self._queue:
                return None
            task_id = self._queue.popleft()
            task = self._tasks[task_id]
            if task.status != TaskStatus.QUEUED:
                raise RuntimeError(f"task {task_id} is not queued")
            task.status = TaskStatus.RUNNING
            task.started_at = utc_now()
            return self._copy(task)

    def succeed(self, task_id: str, result_json: dict, runtime_ms: float) -> TaskRecord:
        return self._finish(
            task_id,
            expected=TaskStatus.RUNNING,
            target=TaskStatus.SUCCEEDED,
            result_json=result_json,
            error_type=None,
            runtime_ms=runtime_ms,
        )

    def fail(self, task_id: str, error_type: str, runtime_ms: float) -> TaskRecord:
        return self._finish(
            task_id,
            expected=TaskStatus.RUNNING,
            target=TaskStatus.FAILED,
            result_json=None,
            error_type=error_type,
            runtime_ms=runtime_ms,
        )

    def _finish(
        self,
        task_id: str,
        expected: TaskStatus,
        target: TaskStatus,
        result_json: dict | None,
        error_type: str | None,
        runtime_ms: float,
    ) -> TaskRecord:
        with self._lock:
            task = self._tasks[task_id]
            if task.status != expected:
                raise RuntimeError(
                    f"compare-and-set failed for {task_id}: expected {expected}, got {task.status}"
                )
            task.status = target
            task.result_json = result_json
            task.error_type = error_type
            task.runtime_ms = runtime_ms
            task.finished_at = utc_now()
            return self._copy(task)

    def metrics(self, run_id: str | None = None) -> tuple[TaskMetricsSnapshot, int]:
        with self._lock:
            counts = {status: 0 for status in TaskStatus}
            runtimes: list[float] = []
            queue_waits: list[float] = []
            completed_last_minute = 0
            now = utc_now()
            selected = [
                task
                for task in self._tasks.values()
                if run_id is None or task.input_json.get("run_id") == run_id
            ]
            for task in selected:
                counts[task.status] += 1
                if task.runtime_ms is not None:
                    runtimes.append(task.runtime_ms)
                if task.queue_wait_ms is not None:
                    queue_waits.append(task.queue_wait_ms)
                if (
                    task.finished_at is not None
                    and (now - task.finished_at).total_seconds() <= 60
                ):
                    completed_last_minute += 1
            busy_time_ms = sum(
                (task.finished_at - task.started_at).total_seconds() * 1_000
                for task in selected
                if task.started_at is not None and task.finished_at is not None
            )
            finished = [task.finished_at for task in selected if task.finished_at is not None]
            observation_window_ms = None
            if selected and finished:
                observation_window_ms = (
                    max(finished) - min(task.created_at for task in selected)
                ).total_seconds() * 1_000
            snapshot = TaskMetricsSnapshot(
                task_count=len(selected),
                status_counts=counts,
                average_queue_wait_ms=(
                    sum(queue_waits) / len(queue_waits) if queue_waits else None
                ),
                p95_queue_wait_ms=linear_percentile(queue_waits, 0.95),
                p99_queue_wait_ms=linear_percentile(queue_waits, 0.99),
                average_runtime_ms=sum(runtimes) / len(runtimes) if runtimes else None,
                p95_runtime_ms=linear_percentile(runtimes, 0.95),
                p99_runtime_ms=linear_percentile(runtimes, 0.99),
                worker_busy_time_ms=busy_time_ms if finished else None,
                observation_window_ms=observation_window_ms,
                completed_last_minute=completed_last_minute,
                pending_outbox_count=0,
            )
            return snapshot, len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._idempotency.clear()
            self._queue.clear()

    @staticmethod
    def _copy(task: TaskRecord) -> TaskRecord:
        return task.model_copy(deep=True)


store = InMemoryTaskStore()
