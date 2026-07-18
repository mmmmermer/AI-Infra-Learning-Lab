from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status

from .models import MetricsResponse, TaskCreate, TaskRecord, TaskStatus
from .repository import repository
from .security import Principal, get_principal, require_scope


app = FastAPI(title="E02 Task API", version="0.2.0")


@app.post(
    "/tasks",
    response_model=TaskRecord,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"description": "Authentication required"}, 403: {"description": "Insufficient scope"}},
)
def create_task(
    payload: TaskCreate,
    principal: Annotated[Principal, Depends(get_principal)],
) -> TaskRecord:
    require_scope(principal, "tasks:write")
    task = TaskRecord(
        task_id=str(uuid4()),
        task_type=payload.task_type,
        priority=payload.priority,
        estimated_duration_ms=payload.estimated_duration_ms,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    return repository.create(task, principal)


@app.get(
    "/tasks/{task_id}",
    response_model=TaskRecord,
    responses={401: {"description": "Authentication required"}, 403: {"description": "Insufficient scope"}},
)
def get_task(
    task_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
) -> TaskRecord:
    require_scope(principal, "tasks:read")
    task = repository.get_for_principal(task_id, principal)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task


@app.get(
    "/metrics",
    response_model=MetricsResponse,
    responses={401: {"description": "Authentication required"}, 403: {"description": "Insufficient scope"}},
)
def get_metrics(
    principal: Annotated[Principal, Depends(get_principal)],
) -> MetricsResponse:
    require_scope(principal, "metrics:read")
    task_count, status_counts = repository.metrics_for_principal(principal)
    return MetricsResponse(task_count=task_count, status_counts=status_counts)
