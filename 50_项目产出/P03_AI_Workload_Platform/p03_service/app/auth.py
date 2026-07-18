from __future__ import annotations

from dataclasses import dataclass


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    allowed_permission_groups: tuple[str, ...]
    can_operate: bool = False


# Development-only identities. The API resolves permissions on the server and
# never accepts tenant, user, or permission groups from the task payload.
REFERENCE_PRINCIPALS = {
    "reference-public-token": Principal(
        tenant_id="tenant-reference",
        user_id="user-public",
        allowed_permission_groups=("public",),
    ),
    "reference-compliance-token": Principal(
        tenant_id="tenant-reference",
        user_id="user-compliance",
        allowed_permission_groups=("compliance_private", "public"),
    ),
    "reference-empty-token": Principal(
        tenant_id="tenant-empty",
        user_id="user-empty",
        allowed_permission_groups=("public",),
    ),
    "reference-other-token": Principal(
        tenant_id="tenant-other",
        user_id="user-other",
        allowed_permission_groups=("public",),
    ),
    "reference-ops-token": Principal(
        tenant_id="tenant-reference",
        user_id="user-ops",
        allowed_permission_groups=("public",),
        can_operate=True,
    ),
}


def authenticate(authorization: str | None) -> Principal:
    if authorization is None:
        raise AuthenticationError("missing_bearer_token")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("invalid_authorization_header")
    principal = REFERENCE_PRINCIPALS.get(token)
    if principal is None:
        raise AuthenticationError("invalid_bearer_token")
    return principal
