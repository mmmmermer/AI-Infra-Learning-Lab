from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .cache import Principal
from .database import TaskDatabase


REFERENCE_PRINCIPALS = {
    "reference-public-token": Principal(
        tenant_id="tenant-reference",
        user_id="user-public",
        permission_groups=("public",),
        acl_version="acl-v1",
    ),
    "reference-compliance-token": Principal(
        tenant_id="tenant-reference",
        user_id="user-compliance",
        permission_groups=("compliance_private", "public"),
        acl_version="acl-v1",
    ),
    "reference-other-tenant-token": Principal(
        tenant_id="tenant-other",
        user_id="user-public",
        permission_groups=("public",),
        acl_version="acl-v1",
    ),
}


class RagTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2_000)
    collection_id: str = Field(min_length=1, max_length=128)
    top_k: int = Field(ge=1, le=20)


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_type: Literal["rag_retrieval"]
    priority: int = Field(default=5, ge=1, le=10)
    estimated_duration_ms: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    max_retries: int = Field(default=2, ge=0, le=100)
    input_json: RagTaskInput


def create_app(
    database: TaskDatabase,
    *,
    token_principals: dict[str, Principal] | None = None,
) -> FastAPI:
    app = FastAPI(title="E06 Async Task Reference", version="0.3.0")
    app.state.database = database
    app.state.token_principals = dict(token_principals or REFERENCE_PRINCIPALS)

    def current_principal(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Principal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication_required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization.removeprefix("Bearer ")
        principal = request.app.state.token_principals.get(token)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return principal

    @app.post("/tasks", status_code=status.HTTP_201_CREATED)
    def create_task(
        payload: CreateTaskRequest,
        response: Response,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> dict:
        task_id, created = database.submit_task(
            payload.idempotency_key,
            payload.input_json.model_dump(),
            max_retries=payload.max_retries,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            allowed_permission_groups=principal.permission_groups,
            acl_version=principal.acl_version,
            task_type=payload.task_type,
            priority=payload.priority,
            estimated_duration_ms=payload.estimated_duration_ms,
        )
        if not created:
            response.status_code = status.HTTP_200_OK
        task = database.get_task(
            task_id,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        assert task is not None
        return {"task": _serialize_task(task), "created_new": created}

    @app.get("/tasks/{task_id}")
    def get_task(
        task_id: str,
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> dict:
        task = database.get_task(
            task_id,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="task_not_found",
            )
        return _serialize_task(task)

    return app


def _serialize_task(task: dict) -> dict:
    import json

    return {
        "task_id": task["task_id"],
        "tenant_id": task["tenant_id"],
        "user_id": task["user_id"],
        "allowed_permission_groups": json.loads(
            task["allowed_permission_groups_json"]
        ),
        "acl_version": task["acl_version"],
        "task_type": task["task_type"],
        "priority": task["priority"],
        "estimated_duration_ms": task["estimated_duration_ms"],
        "idempotency_key": task["idempotency_key"],
        "status": task["status"],
        "input_json": json.loads(task["input_json"]),
        "result_json": (
            json.loads(task["result_json"]) if task["result_json"] is not None else None
        ),
        "error_type": task["error_type"],
        "last_error": task["last_error"],
        "retry_count": task["retry_count"],
        "max_retries": task["max_retries"],
        "created_at": task["created_at"],
        "queued_at": task["queued_at"],
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
        "version": task["version"],
    }
