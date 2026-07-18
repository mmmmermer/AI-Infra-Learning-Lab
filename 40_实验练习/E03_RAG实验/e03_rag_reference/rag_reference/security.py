from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class Principal:
    """Verified identity and effective authorization supplied by the server."""

    tenant_id: str
    user_id: str
    scopes: frozenset[str]
    effective_permission_groups: frozenset[str]
    acl_version: str

    def __post_init__(self) -> None:
        required_strings = {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "acl_version": self.acl_version,
        }
        for field_name, value in required_strings.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if not self.effective_permission_groups:
            raise ValueError("effective_permission_groups must not be empty")

    def acl_fingerprint(self) -> str:
        payload = json.dumps(
            {
                "tenant_id": self.tenant_id,
                "permission_groups": sorted(self.effective_permission_groups),
                "acl_version": self.acl_version,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class AuthenticationRequired(PermissionError):
    status_code = 401


class InsufficientScope(PermissionError):
    status_code = 403


def require_scope(principal: Principal | None, scope: str) -> Principal:
    if principal is None:
        raise AuthenticationRequired("authentication_required")
    if scope not in principal.scopes:
        raise InsufficientScope(f"missing_scope:{scope}")
    return principal
