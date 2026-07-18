from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Annotated, Callable
from uuid import uuid4

from fastapi import Depends, Request

from .context import RequestContext
from .rate_limit import FixedWindowRateLimiter
from .repository import TaskRepository, repository
from .security import Principal, get_principal
from .service import TaskService


@dataclass(frozen=True)
class AppContainer:
    repository: TaskRepository
    limiter: FixedWindowRateLimiter
    clock: Callable[[], float] = monotonic
    now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    id_factory: Callable[[], str] = lambda: str(uuid4())

    @classmethod
    def default(cls) -> "AppContainer":
        return cls(
            repository=repository,
            limiter=FixedWindowRateLimiter(),
        )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_task_service(
    container: Annotated[AppContainer, Depends(get_container)],
) -> TaskService:
    return TaskService(
        repository=container.repository,
        clock=container.clock,
        now_factory=container.now_factory,
        id_factory=container.id_factory,
    )


def get_rate_limiter(
    container: Annotated[AppContainer, Depends(get_container)],
) -> FixedWindowRateLimiter:
    return container.limiter


def get_request_context(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> RequestContext:
    return RequestContext(
        request_id=request.state.request_id,
        principal=principal,
        deadline_at=request.state.deadline_at,
    )
