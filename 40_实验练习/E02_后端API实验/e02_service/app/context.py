from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .errors import AppError
from .security import Principal


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    principal: Principal
    deadline_at: float | None

    def ensure_active(self, clock: Callable[[], float]) -> None:
        if self.deadline_at is not None and clock() >= self.deadline_at:
            raise AppError(
                status_code=504,
                code="deadline_exceeded",
                title="Request deadline exceeded",
                detail="The request deadline expired before the operation could commit.",
            )
