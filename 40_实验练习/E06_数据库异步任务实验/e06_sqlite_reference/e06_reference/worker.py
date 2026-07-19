from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .database import TaskDatabase, TaskStatus, utc_now


@dataclass(frozen=True)
class TaskFailure(Exception):
    error_type: str
    message: str


@dataclass(frozen=True)
class WorkerRun:
    task_id: str
    status: TaskStatus


class ReferenceWorker:
    """Runs one already-dispatched E06 task under the database lease contract."""

    def __init__(
        self,
        database: TaskDatabase,
        *,
        worker_id: str,
        lease_seconds: int = 30,
        now_factory: Callable[[], datetime] = utc_now,
    ) -> None:
        if not worker_id:
            raise ValueError("worker_id must be non-empty")
        self.database = database
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.now_factory = now_factory

    def run_once(self, handler: Callable[[dict], dict]) -> WorkerRun | None:
        started_at = self.now_factory()
        task = self.database.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
            now=started_at,
        )
        if task is None:
            return None

        try:
            result = handler(task)
        except TaskFailure as error:
            status = self.database.fail_task(
                task["task_id"],
                self.worker_id,
                task["version"],
                error.error_type,
                now=self.now_factory(),
                error_message=error.message,
            )
            return WorkerRun(task["task_id"], status)

        self.database.complete_task(
            task["task_id"],
            self.worker_id,
            task["version"],
            result,
            now=self.now_factory(),
        )
        return WorkerRun(task["task_id"], TaskStatus.SUCCEEDED)
