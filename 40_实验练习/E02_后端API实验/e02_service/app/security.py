from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import AppError


logger = logging.getLogger("e02.audit")


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    scopes: frozenset[str]

    @property
    def subject_ref(self) -> str:
        raw_subject = f"{self.tenant_id}:{self.user_id}".encode()
        return sha256(raw_subject).hexdigest()[:12]


# These short fixture credentials are intentionally non-secret. A production service
# must validate a signed token's issuer, audience, expiry, and revocation state.
_FIXTURE_PRINCIPALS = {
    "alice-fixture": Principal(
        tenant_id="tenant-demo",
        user_id="alice",
        scopes=frozenset({"tasks:read", "tasks:write", "metrics:read"}),
    ),
    "bob-fixture": Principal(
        tenant_id="tenant-demo",
        user_id="bob",
        scopes=frozenset({"tasks:read", "tasks:write", "metrics:read"}),
    ),
    "carol-fixture": Principal(
        tenant_id="tenant-other",
        user_id="carol",
        scopes=frozenset({"tasks:read", "tasks:write", "metrics:read"}),
    ),
    "reader-fixture": Principal(
        tenant_id="tenant-demo",
        user_id="reader",
        scopes=frozenset({"tasks:read"}),
    ),
}

_bearer = HTTPBearer(auto_error=False)


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            status_code=401,
            code="authentication_required",
            title="Authentication required",
            detail="A bearer credential is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = _FIXTURE_PRINCIPALS.get(credentials.credentials)
    if principal is None:
        raise AppError(
            status_code=401,
            code="invalid_credentials",
            title="Invalid credentials",
            detail="The bearer credential is not valid for this reference service.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.subject_ref = principal.subject_ref
    logger.info(
        "principal_resolved",
        extra={
            "stage": "security",
            "request_id": request.state.request_id,
            "subject_ref": principal.subject_ref,
        },
    )
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise AppError(
            status_code=403,
            code="insufficient_scope",
            title="Insufficient scope",
            detail=f"The principal lacks the required {scope!r} scope.",
        )
