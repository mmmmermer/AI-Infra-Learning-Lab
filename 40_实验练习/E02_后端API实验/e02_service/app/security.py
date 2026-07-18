from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    scopes: frozenset[str]


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
    "reader-fixture": Principal(
        tenant_id="tenant-demo",
        user_id="reader",
        scopes=frozenset({"tasks:read"}),
    ),
}

_bearer = HTTPBearer(auto_error=False)


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="authentication_required")
    principal = _FIXTURE_PRINCIPALS.get(credentials.credentials)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise HTTPException(status_code=403, detail="insufficient_scope")
