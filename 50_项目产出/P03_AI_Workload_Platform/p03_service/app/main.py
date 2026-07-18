from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from .auth import AuthenticationError, Principal, authenticate
from .models import (
    MetricsResponse,
    SubmissionResponse,
    TaskCreate,
    TaskRecord,
    TaskStatus,
    WorkerRunResponse,
)
from .postgres_store import PostgresTaskStore
from .redis_queue import RedisTaskQueue
from .settings import Settings
from .store import store
from .worker import execute_next


settings = Settings.from_env()
if settings.backend == "memory":
    task_store = store
    task_queue: RedisTaskQueue | None = None
else:
    task_store = PostgresTaskStore(settings.database_url)
    task_queue = RedisTaskQueue(settings.redis_url, settings.redis_queue_key)

app = FastAPI(title="P03 Workload Platform", version="0.3.1")


def current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    try:
        return authenticate(authorization)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def operator_principal(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    if not principal.can_operate:
        raise HTTPException(status_code=403, detail="operator_permission_required")
    return principal


@app.post("/tasks", response_model=SubmissionResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_task(
    payload: TaskCreate,
    principal: Annotated[Principal, Depends(current_principal)],
) -> SubmissionResponse:
    task, created_new = task_store.submit(payload, principal)
    return SubmissionResponse(task=task, created_new=created_new)


@app.get("/tasks/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> TaskRecord:
    task = task_store.get(task_id, principal.tenant_id, principal.user_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task


@app.post("/workers/run-next", response_model=WorkerRunResponse | None)
def run_next_task(
    _principal: Annotated[Principal, Depends(operator_principal)],
) -> WorkerRunResponse | None:
    if settings.backend != "memory":
        raise HTTPException(status_code=409, detail="independent_worker_enabled")
    task = execute_next(store)
    if task is None:
        return None
    return WorkerRunResponse(
        task_id=task.task_id,
        status=task.status,
        error_type=task.error_type,
    )


@app.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    _principal: Annotated[Principal, Depends(operator_principal)],
    run_id: str | None = Query(default=None, max_length=128),
) -> MetricsResponse:
    if settings.backend == "memory":
        snapshot, broker_queue_length = store.metrics(run_id=run_id)
    else:
        assert isinstance(task_store, PostgresTaskStore)
        assert task_queue is not None
        try:
            snapshot = task_store.metrics(run_id=run_id)
            broker_queue_length = task_queue.length()
        except Exception as error:
            raise HTTPException(status_code=503, detail="metrics_dependency_unavailable") from error
    return MetricsResponse(
        task_count=snapshot.task_count,
        broker_queue_length=broker_queue_length,
        queue_length=broker_queue_length,
        active_workers=snapshot.status_counts[TaskStatus.RUNNING],
        pending_outbox_count=snapshot.pending_outbox_count,
        completed_last_minute=snapshot.completed_last_minute,
        status_counts=snapshot.status_counts,
        average_queue_wait_ms=snapshot.average_queue_wait_ms,
        p95_queue_wait_ms=snapshot.p95_queue_wait_ms,
        p99_queue_wait_ms=snapshot.p99_queue_wait_ms,
        average_runtime_ms=snapshot.average_runtime_ms,
        p95_runtime_ms=snapshot.p95_runtime_ms,
        p99_runtime_ms=snapshot.p99_runtime_ms,
        worker_busy_time_ms=snapshot.worker_busy_time_ms,
        observation_window_ms=snapshot.observation_window_ms,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    if settings.backend == "memory":
        return {"status": "ready", "backend": "memory"}
    assert isinstance(task_store, PostgresTaskStore)
    assert task_queue is not None
    try:
        database_ready = task_store.ping()
        redis_ready = task_queue.ping()
    except Exception as error:
        raise HTTPException(status_code=503, detail="dependency_unavailable") from error
    if not database_ready or not redis_ready:
        raise HTTPException(status_code=503, detail="dependency_unavailable")
    return {"status": "ready", "backend": "postgres_redis"}
