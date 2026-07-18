from __future__ import annotations

import logging
from pathlib import Path
import re
import traceback
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .context import RequestContext
from .dependencies import (
    AppContainer,
    get_rate_limiter,
    get_request_context,
    get_task_service,
)
from .errors import AppError
from .models import (
    HealthResponse,
    InvalidParameter,
    MetricsResponse,
    ProblemDetails,
    TaskCreate,
    TaskPage,
    TaskPatch,
    TaskRecord,
)
from .rate_limit import FixedWindowRateLimiter
from .service import TaskService


logger = logging.getLogger("e02.audit")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ETAG_PATTERN = re.compile(r'^"([1-9][0-9]*)"$')


def _inline_local_schema_refs(schema: dict[str, object]) -> dict[str, object]:
    """Make a Pydantic schema safe to embed below an OpenAPI response node."""
    local_defs = schema.pop("$defs", {})

    def resolve(node: object) -> object:
        if isinstance(node, list):
            return [resolve(item) for item in node]
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            definition_name = reference.removeprefix("#/$defs/")
            definition = local_defs.get(definition_name)
            if definition is None:
                raise ValueError(f"unknown local schema definition: {definition_name}")
            return resolve(definition)
        return {key: resolve(value) for key, value in node.items()}

    resolved = resolve(schema)
    if not isinstance(resolved, dict):
        raise TypeError("the root model schema must be an object")
    return resolved


PROBLEM_SCHEMA = _inline_local_schema_refs(ProblemDetails.model_json_schema())


def _problem_contract(description: str) -> dict[str, object]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": PROBLEM_SCHEMA,
            }
        },
    }


PROBLEM_RESPONSES = {
    400: _problem_contract("Invalid request metadata"),
    401: _problem_contract("Authentication required"),
    403: _problem_contract("Insufficient scope"),
    404: _problem_contract("Resource not found"),
    409: _problem_contract("Idempotency conflict"),
    412: _problem_contract("Version conflict"),
    422: _problem_contract("Validation failure"),
    429: _problem_contract("Rate limit exceeded"),
    500: _problem_contract("Unexpected internal failure"),
    503: _problem_contract("Dependency unavailable"),
    504: _problem_contract("Deadline exceeded"),
}


def _problem_response(
    request: Request,
    error: AppError,
    *,
    invalid_params: list[InvalidParameter] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid4().hex)
    body = ProblemDetails(
        type=f"urn:e02:problem:{error.code}",
        title=error.title,
        status=error.status_code,
        detail=error.detail,
        code=error.code,
        request_id=request_id,
        retry_after_ms=error.retry_after_ms,
        invalid_params=invalid_params,
    )
    headers = {**error.headers, "X-Request-ID": request_id}
    logger.warning(
        "request_failed",
        extra={
            "stage": "error_response",
            "request_id": request_id,
            "subject_ref": getattr(request.state, "subject_ref", "anonymous"),
            "error_code": error.code,
        },
    )
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
        media_type="application/problem+json",
    )


def _consume_rate_limit(
    limiter: FixedWindowRateLimiter,
    context: RequestContext,
) -> None:
    decision = limiter.consume(context.principal.subject_ref)
    if decision.allowed:
        return
    retry_seconds = max(1, (decision.retry_after_ms + 999) // 1000)
    raise AppError(
        status_code=429,
        code="rate_limit_exceeded",
        title="Rate limit exceeded",
        detail="The mutation rate limit has been reached; retry after the window resets.",
        headers={"Retry-After": str(retry_seconds)},
        retry_after_ms=decision.retry_after_ms,
    )


def _parse_if_match(value: str) -> int:
    match = ETAG_PATTERN.fullmatch(value)
    if match is None:
        raise AppError(
            status_code=400,
            code="invalid_if_match",
            title="Invalid If-Match header",
            detail='If-Match must contain one quoted positive version, for example "1".',
        )
    return int(match.group(1))


def _exception_frame_locations(error: Exception) -> tuple[str, ...]:
    return tuple(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(error.__traceback__)
    )


def create_app(container: AppContainer | None = None) -> FastAPI:
    application = FastAPI(title="E02 Task API", version="0.3.0")
    application.state.container = container or AppContainer.default()

    @application.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        incoming_request_id = request.headers.get("X-Request-ID")
        if incoming_request_id is not None and not REQUEST_ID_PATTERN.fullmatch(
            incoming_request_id
        ):
            request.state.request_id = uuid4().hex
            request.state.deadline_at = None
            return _problem_response(
                request,
                AppError(
                    status_code=400,
                    code="invalid_request_id",
                    title="Invalid request ID",
                    detail="X-Request-ID must use 1-64 letters, digits, dots, underscores, or hyphens.",
                ),
            )

        request.state.request_id = incoming_request_id or uuid4().hex
        deadline_header = request.headers.get("X-Request-Deadline-Ms")
        request.state.deadline_at = None
        if deadline_header is not None:
            try:
                deadline_ms = int(deadline_header)
            except ValueError:
                deadline_ms = 0
            if not 1 <= deadline_ms <= 60_000:
                return _problem_response(
                    request,
                    AppError(
                        status_code=400,
                        code="invalid_deadline",
                        title="Invalid request deadline",
                        detail="X-Request-Deadline-Ms must be an integer from 1 through 60000.",
                    ),
                )
            request.state.deadline_at = (
                request.app.state.container.clock() + deadline_ms / 1000
            )

        logger.info(
            "request_started",
            extra={
                "stage": "entry",
                "request_id": request.state.request_id,
                "subject_ref": "anonymous",
            },
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "request_completed",
            extra={
                "stage": "entry",
                "request_id": request.state.request_id,
                "subject_ref": getattr(request.state, "subject_ref", "anonymous"),
                "status_code": response.status_code,
            },
        )
        return response

    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
        return _problem_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        invalid_params = [
            InvalidParameter(
                location=[part for part in item["loc"]],
                reason=item["type"],
            )
            for item in error.errors()
        ]
        return _problem_response(
            request,
            AppError(
                status_code=422,
                code="invalid_request",
                title="Request validation failed",
                detail="One or more request fields violate the API contract.",
            ),
            invalid_params=invalid_params,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            "unexpected_error",
            extra={
                "stage": "error_response",
                "request_id": getattr(request.state, "request_id", "unknown"),
                "subject_ref": getattr(request.state, "subject_ref", "anonymous"),
                "exception_type": type(error).__name__,
                "exception_frames": _exception_frame_locations(error),
            },
        )
        return _problem_response(
            request,
            AppError(
                status_code=500,
                code="internal_error",
                title="Internal server error",
                detail="The service failed without exposing internal exception details.",
            ),
        )

    @application.get(
        "/livez",
        response_model=HealthResponse,
        responses={
            code: PROBLEM_RESPONSES[code]
            for code in (400, 500)
        },
    )
    def get_liveness() -> HealthResponse:
        return HealthResponse(status="ok", dependency="not_checked")

    @application.get(
        "/readyz",
        response_model=HealthResponse,
        responses={
            code: PROBLEM_RESPONSES[code]
            for code in (400, 500, 503)
        },
    )
    def get_readiness(
        service: Annotated[TaskService, Depends(get_task_service)],
    ) -> HealthResponse:
        service.ensure_ready()
        return HealthResponse(status="ready", dependency="task_repository")

    @application.post(
        "/tasks",
        response_model=TaskRecord,
        status_code=status.HTTP_201_CREATED,
        responses={200: {"model": TaskRecord, "description": "Idempotent replay"}, **PROBLEM_RESPONSES},
    )
    def create_task(
        response: Response,
        payload: TaskCreate,
        context: Annotated[RequestContext, Depends(get_request_context)],
        service: Annotated[TaskService, Depends(get_task_service)],
        limiter: Annotated[FixedWindowRateLimiter, Depends(get_rate_limiter)],
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=128),
        ] = None,
    ) -> TaskRecord:
        _consume_rate_limit(limiter, context)
        outcome = service.create_task(
            payload,
            context,
            idempotency_key=idempotency_key,
        )
        response.status_code = 200 if outcome.replayed else 201
        response.headers["ETag"] = f'"{outcome.record.version}"'
        response.headers["Idempotency-Replayed"] = str(outcome.replayed).lower()
        return outcome.record

    @application.get(
        "/tasks",
        response_model=TaskPage,
        responses=PROBLEM_RESPONSES,
    )
    def list_tasks(
        context: Annotated[RequestContext, Depends(get_request_context)],
        service: Annotated[TaskService, Depends(get_task_service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
    ) -> TaskPage:
        return service.list_tasks(context, limit=limit, cursor=cursor)

    @application.get(
        "/tasks/{task_id}",
        response_model=TaskRecord,
        responses=PROBLEM_RESPONSES,
    )
    def get_task(
        task_id: str,
        response: Response,
        context: Annotated[RequestContext, Depends(get_request_context)],
        service: Annotated[TaskService, Depends(get_task_service)],
    ) -> TaskRecord:
        task = service.get_task(task_id, context)
        response.headers["ETag"] = f'"{task.version}"'
        return task

    @application.patch(
        "/tasks/{task_id}",
        response_model=TaskRecord,
        responses=PROBLEM_RESPONSES,
    )
    def update_task(
        task_id: str,
        payload: TaskPatch,
        response: Response,
        if_match: Annotated[str, Header(alias="If-Match")],
        context: Annotated[RequestContext, Depends(get_request_context)],
        service: Annotated[TaskService, Depends(get_task_service)],
        limiter: Annotated[FixedWindowRateLimiter, Depends(get_rate_limiter)],
    ) -> TaskRecord:
        _consume_rate_limit(limiter, context)
        task = service.update_task(
            task_id,
            payload,
            context,
            expected_version=_parse_if_match(if_match),
        )
        response.headers["ETag"] = f'"{task.version}"'
        return task

    @application.get(
        "/metrics",
        response_model=MetricsResponse,
        responses=PROBLEM_RESPONSES,
    )
    def get_metrics(
        context: Annotated[RequestContext, Depends(get_request_context)],
        service: Annotated[TaskService, Depends(get_task_service)],
    ) -> MetricsResponse:
        return service.get_metrics(context)

    return application


app = create_app()
