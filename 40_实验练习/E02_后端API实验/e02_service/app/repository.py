from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from .models import TaskRecord, TaskStatus
from .security import Principal


@dataclass(frozen=True)
class OwnedTask:
    tenant_id: str
    user_id: str
    record: TaskRecord


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, OwnedTask] = {}
        self._lock = RLock()

    def create(self, task: TaskRecord, principal: Principal) -> TaskRecord:
        with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"duplicate task_id: {task.task_id}")
            self._tasks[task.task_id] = OwnedTask(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                record=task,
            )
            return task

    def get_for_principal(self, task_id: str, principal: Principal) -> TaskRecord | None:
        with self._lock:
            owned = self._tasks.get(task_id)
            if owned is None:
                return None
            if (owned.tenant_id, owned.user_id) != (
                principal.tenant_id,
                principal.user_id,
            ):
                return None
            return owned.record

    def list_for_principal(self, principal: Principal) -> list[TaskRecord]:
        with self._lock:
            return [
                owned.record
                for owned in self._tasks.values()
                if (owned.tenant_id, owned.user_id)
                == (principal.tenant_id, principal.user_id)
            ]

    def metrics_for_principal(
        self, principal: Principal
    ) -> tuple[int, dict[TaskStatus, int]]:
        with self._lock:
            counts = {status: 0 for status in TaskStatus}
            visible = [
                owned.record
                for owned in self._tasks.values()
                if (owned.tenant_id, owned.user_id)
                == (principal.tenant_id, principal.user_id)
            ]
            for task in visible:
                counts[task.status] += 1
            return len(visible), counts

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


repository = TaskRepository()
