from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from threading import BoundedSemaphore, RLock
from time import monotonic

from .models import TaskRecord, TaskStatus
from .security import Principal


logger = logging.getLogger("e02.audit")


class RepositoryUnavailable(Exception):
    pass


class RepositoryCapacityExhausted(Exception):
    pass


class DeadlineExpired(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class VersionConflict(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__(f"current version is {current_version}")
        self.current_version = current_version


class CursorNotFound(Exception):
    pass


@dataclass(frozen=True)
class OwnedTask:
    tenant_id: str
    user_id: str
    record: TaskRecord


@dataclass(frozen=True)
class IdempotencyRecord:
    payload_fingerprint: str
    task_id: str


@dataclass(frozen=True)
class CreateOutcome:
    record: TaskRecord
    replayed: bool


class TaskRepository:
    def __init__(
        self,
        *,
        pool_size: int = 4,
        clock: Callable[[], float] = monotonic,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        if pool_size < 1:
            raise ValueError("pool_size must be positive")
        self._tasks: dict[str, OwnedTask] = {}
        self._idempotency: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self._lock = RLock()
        self._pool = BoundedSemaphore(pool_size)
        self._clock = clock
        self._before_commit = before_commit
        self._available = True

    @contextmanager
    def connection_lease(self) -> Iterator[None]:
        with self._lock:
            if not self._available:
                raise RepositoryUnavailable
        if not self._pool.acquire(blocking=False):
            raise RepositoryCapacityExhausted
        try:
            with self._lock:
                if not self._available:
                    raise RepositoryUnavailable
            yield
        finally:
            self._pool.release()

    def readiness(self) -> tuple[bool, str]:
        try:
            with self.connection_lease():
                return True, "ready"
        except RepositoryUnavailable:
            return False, "unavailable"
        except RepositoryCapacityExhausted:
            return False, "capacity_exhausted"

    def set_available(self, available: bool) -> None:
        with self._lock:
            self._available = available

    def create(
        self,
        task: TaskRecord,
        principal: Principal,
        *,
        request_id: str,
        payload_fingerprint: str,
        idempotency_key: str | None,
        deadline_at: float | None,
    ) -> CreateOutcome:
        with self.connection_lease(), self._lock:
            self._ensure_available_locked()
            idempotency_scope = None
            if idempotency_key is not None:
                idempotency_scope = (
                    principal.tenant_id,
                    principal.user_id,
                    idempotency_key,
                )
                previous = self._idempotency.get(idempotency_scope)
                if previous is not None:
                    if previous.payload_fingerprint != payload_fingerprint:
                        raise IdempotencyConflict
                    outcome = CreateOutcome(
                        record=self._tasks[previous.task_id].record,
                        replayed=True,
                    )
                    self._log("task_create_replayed", request_id, principal)
                    return outcome

            if self._before_commit is not None:
                self._before_commit()
            self._ensure_available_locked()
            if deadline_at is not None and self._clock() >= deadline_at:
                raise DeadlineExpired
            if task.task_id in self._tasks:
                raise ValueError(f"duplicate task_id: {task.task_id}")

            self._tasks[task.task_id] = OwnedTask(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                record=task,
            )
            if idempotency_scope is not None:
                self._idempotency[idempotency_scope] = IdempotencyRecord(
                    payload_fingerprint=payload_fingerprint,
                    task_id=task.task_id,
                )
            self._log("task_created", request_id, principal)
            return CreateOutcome(record=task, replayed=False)

    def get_for_principal(
        self,
        task_id: str,
        principal: Principal,
        *,
        request_id: str,
    ) -> TaskRecord | None:
        with self.connection_lease(), self._lock:
            self._ensure_available_locked()
            owned = self._tasks.get(task_id)
            visible = owned is not None and (
                owned.tenant_id,
                owned.user_id,
            ) == (principal.tenant_id, principal.user_id)
            self._log("task_looked_up", request_id, principal)
            return owned.record if visible and owned is not None else None

    def update_for_principal(
        self,
        task_id: str,
        principal: Principal,
        *,
        request_id: str,
        expected_version: int,
        priority: int,
        deadline_at: float | None,
    ) -> TaskRecord | None:
        with self.connection_lease(), self._lock:
            self._ensure_available_locked()
            owned = self._tasks.get(task_id)
            if owned is None or (owned.tenant_id, owned.user_id) != (
                principal.tenant_id,
                principal.user_id,
            ):
                self._log("task_update_not_visible", request_id, principal)
                return None
            if owned.record.version != expected_version:
                raise VersionConflict(owned.record.version)
            if self._before_commit is not None:
                self._before_commit()
            self._ensure_available_locked()
            if deadline_at is not None and self._clock() >= deadline_at:
                raise DeadlineExpired

            updated = owned.record.model_copy(
                update={"priority": priority, "version": owned.record.version + 1}
            )
            self._tasks[task_id] = OwnedTask(
                tenant_id=owned.tenant_id,
                user_id=owned.user_id,
                record=updated,
            )
            self._log("task_updated", request_id, principal)
            return updated

    def list_for_principal(
        self,
        principal: Principal,
        *,
        request_id: str,
        limit: int,
        after_task_id: str | None,
    ) -> tuple[list[TaskRecord], str | None]:
        with self.connection_lease(), self._lock:
            self._ensure_available_locked()
            visible = sorted(
                (
                    owned.record
                    for owned in self._tasks.values()
                    if (owned.tenant_id, owned.user_id)
                    == (principal.tenant_id, principal.user_id)
                ),
                key=lambda task: task.task_id,
            )
            start = 0
            if after_task_id is not None:
                positions = [
                    index
                    for index, task in enumerate(visible)
                    if task.task_id == after_task_id
                ]
                if not positions:
                    raise CursorNotFound
                start = positions[0] + 1
            page = visible[start : start + limit]
            has_more = start + limit < len(visible)
            next_task_id = page[-1].task_id if page and has_more else None
            self._log("task_page_read", request_id, principal)
            return page, next_task_id

    def metrics_for_principal(
        self,
        principal: Principal,
        *,
        request_id: str,
    ) -> tuple[int, dict[TaskStatus, int]]:
        with self.connection_lease(), self._lock:
            self._ensure_available_locked()
            counts = {status: 0 for status in TaskStatus}
            visible = [
                owned.record
                for owned in self._tasks.values()
                if (owned.tenant_id, owned.user_id)
                == (principal.tenant_id, principal.user_id)
            ]
            for task in visible:
                counts[task.status] += 1
            self._log("task_metrics_read", request_id, principal)
            return len(visible), counts

    def count_all(self) -> int:
        with self._lock:
            return len(self._tasks)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._idempotency.clear()
            self._available = True

    def _ensure_available_locked(self) -> None:
        if not self._available:
            raise RepositoryUnavailable

    @staticmethod
    def _log(event: str, request_id: str, principal: Principal) -> None:
        logger.info(
            event,
            extra={
                "stage": "repository",
                "request_id": request_id,
                "subject_ref": principal.subject_ref,
            },
        )


repository = TaskRepository()
