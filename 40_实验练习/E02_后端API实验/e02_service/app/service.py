from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from hashlib import sha256
import json
import logging
import re
from time import monotonic
from typing import Callable
from uuid import uuid4

from .context import RequestContext
from .errors import AppError
from .models import MetricsResponse, TaskCreate, TaskPage, TaskPatch, TaskRecord, TaskStatus
from .repository import (
    CreateOutcome,
    CursorNotFound,
    DeadlineExpired,
    IdempotencyConflict,
    RepositoryCapacityExhausted,
    RepositoryUnavailable,
    TaskRepository,
    VersionConflict,
)
from .security import require_scope


logger = logging.getLogger("e02.audit")
CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class TaskService:
    repository: TaskRepository
    clock: Callable[[], float] = monotonic
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    id_factory: Callable[[], str] = lambda: str(uuid4())

    def create_task(
        self,
        payload: TaskCreate,
        context: RequestContext,
        *,
        idempotency_key: str | None,
    ) -> CreateOutcome:
        require_scope(context.principal, "tasks:write")
        context.ensure_active(self.clock)
        self._log("task_create_started", context)
        task = TaskRecord(
            task_id=self.id_factory(),
            task_type=payload.task_type,
            priority=payload.priority,
            estimated_duration_ms=payload.estimated_duration_ms,
            status=TaskStatus.PENDING,
            created_at=self.now_factory(),
            version=1,
        )
        fingerprint = sha256(
            json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            return self.repository.create(
                task,
                context.principal,
                request_id=context.request_id,
                payload_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
                deadline_at=context.deadline_at,
            )
        except IdempotencyConflict as exc:
            raise AppError(
                status_code=409,
                code="idempotency_key_conflict",
                title="Idempotency key conflict",
                detail="The idempotency key was already used with a different payload.",
            ) from exc
        except DeadlineExpired as exc:
            raise self._deadline_error() from exc
        except (RepositoryUnavailable, RepositoryCapacityExhausted) as exc:
            raise self._dependency_error(exc) from exc

    def get_task(self, task_id: str, context: RequestContext) -> TaskRecord:
        require_scope(context.principal, "tasks:read")
        context.ensure_active(self.clock)
        self._log("task_read_started", context)
        try:
            task = self.repository.get_for_principal(
                task_id,
                context.principal,
                request_id=context.request_id,
            )
        except (RepositoryUnavailable, RepositoryCapacityExhausted) as exc:
            raise self._dependency_error(exc) from exc
        if task is None:
            raise AppError(
                status_code=404,
                code="task_not_found",
                title="Task not found",
                detail="The task does not exist or is not visible to this principal.",
            )
        return task

    def update_task(
        self,
        task_id: str,
        payload: TaskPatch,
        context: RequestContext,
        *,
        expected_version: int,
    ) -> TaskRecord:
        require_scope(context.principal, "tasks:write")
        context.ensure_active(self.clock)
        self._log("task_update_started", context)
        try:
            task = self.repository.update_for_principal(
                task_id,
                context.principal,
                request_id=context.request_id,
                expected_version=expected_version,
                priority=payload.priority,
                deadline_at=context.deadline_at,
            )
        except VersionConflict as exc:
            raise AppError(
                status_code=412,
                code="version_conflict",
                title="Version conflict",
                detail=f"The task is currently at version {exc.current_version}.",
            ) from exc
        except DeadlineExpired as exc:
            raise self._deadline_error() from exc
        except (RepositoryUnavailable, RepositoryCapacityExhausted) as exc:
            raise self._dependency_error(exc) from exc
        if task is None:
            raise AppError(
                status_code=404,
                code="task_not_found",
                title="Task not found",
                detail="The task does not exist or is not visible to this principal.",
            )
        return task

    def list_tasks(
        self,
        context: RequestContext,
        *,
        limit: int,
        cursor: str | None,
    ) -> TaskPage:
        require_scope(context.principal, "tasks:read")
        context.ensure_active(self.clock)
        self._log("task_list_started", context)
        after_task_id = self._decode_cursor(cursor) if cursor is not None else None
        try:
            items, next_task_id = self.repository.list_for_principal(
                context.principal,
                request_id=context.request_id,
                limit=limit,
                after_task_id=after_task_id,
            )
        except CursorNotFound as exc:
            raise self._invalid_cursor() from exc
        except (RepositoryUnavailable, RepositoryCapacityExhausted) as exc:
            raise self._dependency_error(exc) from exc
        next_cursor = (
            self._encode_cursor(next_task_id) if next_task_id is not None else None
        )
        return TaskPage(items=items, next_cursor=next_cursor)

    def get_metrics(self, context: RequestContext) -> MetricsResponse:
        require_scope(context.principal, "metrics:read")
        context.ensure_active(self.clock)
        self._log("metrics_read_started", context)
        try:
            task_count, status_counts = self.repository.metrics_for_principal(
                context.principal,
                request_id=context.request_id,
            )
        except (RepositoryUnavailable, RepositoryCapacityExhausted) as exc:
            raise self._dependency_error(exc) from exc
        return MetricsResponse(task_count=task_count, status_counts=status_counts)

    def ensure_ready(self) -> None:
        ready, reason = self.repository.readiness()
        if not ready:
            code = (
                "dependency_capacity_exhausted"
                if reason == "capacity_exhausted"
                else "dependency_unavailable"
            )
            raise AppError(
                status_code=503,
                code=code,
                title="Service not ready",
                detail=f"The task repository is {reason}.",
                headers={"Retry-After": "1"},
                retry_after_ms=1000,
            )

    @staticmethod
    def _encode_cursor(task_id: str) -> str:
        return urlsafe_b64encode(task_id.encode()).decode().rstrip("=")

    @classmethod
    def _decode_cursor(cls, cursor: str) -> str:
        if CURSOR_PATTERN.fullmatch(cursor) is None:
            raise cls._invalid_cursor()
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = b64decode(
                (cursor + padding).encode("ascii"),
                altchars=b"-_",
                validate=True,
            ).decode()
        except (Base64Error, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
            raise cls._invalid_cursor() from exc
        if not decoded or cls._encode_cursor(decoded) != cursor:
            raise cls._invalid_cursor()
        return decoded

    @staticmethod
    def _invalid_cursor() -> AppError:
        return AppError(
            status_code=400,
            code="invalid_cursor",
            title="Invalid pagination cursor",
            detail="The cursor is malformed, expired, or not visible to this principal.",
        )
    @staticmethod
    def _dependency_error(
        error: RepositoryUnavailable | RepositoryCapacityExhausted,
    ) -> AppError:
        if isinstance(error, RepositoryCapacityExhausted):
            code = "dependency_capacity_exhausted"
            detail = "The repository connection capacity is exhausted; retry later."
        else:
            code = "dependency_unavailable"
            detail = "The repository dependency is unavailable; retry later."
        return AppError(
            status_code=503,
            code=code,
            title="Dependency unavailable",
            detail=detail,
            headers={"Retry-After": "1"},
            retry_after_ms=1000,
        )

    @staticmethod
    def _deadline_error() -> AppError:
        return AppError(
            status_code=504,
            code="deadline_exceeded",
            title="Request deadline exceeded",
            detail="The request deadline expired before the operation could commit.",
        )

    @staticmethod
    def _log(event: str, context: RequestContext) -> None:
        logger.info(
            event,
            extra={
                "stage": "service",
                "request_id": context.request_id,
                "subject_ref": context.principal.subject_ref,
            },
        )
