from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from e04_runtime import EgressPolicy, PathPolicy, Principal, ResourceGrant, VerifiedClaims
from e04_runtime.errors import UnsafeEgressTarget, UnsafePathTarget
from e04_runtime.models import ExecutionContext, ToolProposal
from e04_runtime.tools import ResourcePolicy, ToolGateway, ToolRegistry, ToolSpec

from conftest import Harness


class TargetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    target: StrictStr


class TargetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    accepted: StrictBool


def target_principal() -> Principal:
    return Principal.from_verified_claims(
        VerifiedClaims(
            tenant_id="tenant-target",
            owner_user_id="owner-target",
            capabilities=("target:read",),
            grants=(ResourceGrant("target:read", "target"),),
        )
    )


def target_gateway(
    *,
    egress_policy: EgressPolicy | None = None,
    path_policy: PathPolicy | None = None,
    use_url: bool = False,
    use_path: bool = False,
) -> tuple[ToolGateway, list[ExecutionContext]]:
    contexts: list[ExecutionContext] = []

    def handler(raw_args, context):  # type: ignore[no-untyped-def]
        TargetArgs.model_validate(raw_args)
        contexts.append(context)
        return {"accepted": True}

    spec = ToolSpec(
        name="read_target",
        args_model=TargetArgs,
        output_model=TargetOutput,
        action="target:read",
        resource_resolver=lambda value: "target",
        handler=handler,
        timeout_seconds=1.0,
        estimated_duration_seconds=0.01,
        url_resolver=(
            (lambda value: TargetArgs.model_validate(value).target) if use_url else None
        ),
        path_resolver=(
            (lambda value: TargetArgs.model_validate(value).target) if use_path else None
        ),
    )
    return (
        ToolGateway(
            ToolRegistry((spec,)),
            ResourcePolicy(),
            egress_policy=egress_policy,
            path_policy=path_policy,
        ),
        contexts,
    )


def execute_target(harness: Harness, gateway: ToolGateway, target: str) -> None:
    gateway.execute(
        principal=target_principal(),
        proposal=ToolProposal(
            tool_name="read_target",
            arguments={"target": target},
        ),
        now=harness.clock.now(),
        deadline_at=harness.clock.now() + timedelta(seconds=5),
    )


def test_egress_is_denied_by_default_and_exact_origin_is_normalized(
    harness: Harness,
) -> None:
    denied, denied_contexts = target_gateway(use_url=True)
    with pytest.raises(UnsafeEgressTarget, match="disabled"):
        execute_target(harness, denied, "https://api.example.com:443/v1")
    assert denied_contexts == []

    allowed, contexts = target_gateway(
        use_url=True,
        egress_policy=EgressPolicy(
            frozenset({("https", "api.example.com", 443)})
        ),
    )
    execute_target(
        harness,
        allowed,
        "HTTPS://API.EXAMPLE.COM:443/v1/items?limit=2",
    )

    assert len(contexts) == 1
    assert contexts[0].normalized_url == (
        "https://api.example.com:443/v1/items?limit=2"
    )
    assert contexts[0].normalized_path is None


@pytest.mark.parametrize(
    "target,origin",
    [
        ("http://127.0.0.1:80/admin", ("http", "127.0.0.1", 80)),
        ("http://169.254.169.254:80/latest/meta-data", ("http", "169.254.169.254", 80)),
        ("http://[::1]:80/admin", ("http", "::1", 80)),
        ("https://metadata.google.internal:443/", ("https", "metadata.google.internal", 443)),
        ("https://user:pass@api.example.com:443/", ("https", "api.example.com", 443)),
        ("https://api.example.com/path", ("https", "api.example.com", 443)),
        ("https://api.example.com:0/path", ("https", "api.example.com", 0)),
        ("file://api.example.com:443/etc/passwd", ("file", "api.example.com", 443)),
        ("https://2130706433:443/", ("https", "2130706433", 443)),
        ("http://127.1:80/admin", ("http", "127.1", 80)),
        ("http://0177.0.0.1:80/admin", ("http", "0177.0.0.1", 80)),
        ("http://0x7f.0.0.1:80/admin", ("http", "0x7f.0.0.1", 80)),
        ("https://api.example.com.evil.test:443/", ("https", "api.example.com", 443)),
    ],
)
def test_ssrf_and_url_parser_confusions_stop_before_handler(
    harness: Harness,
    target: str,
    origin: tuple[str, str, int],
) -> None:
    gateway, contexts = target_gateway(
        use_url=True,
        egress_policy=EgressPolicy(frozenset({origin})),
    )

    with pytest.raises(UnsafeEgressTarget):
        execute_target(harness, gateway, target)

    assert contexts == []


def test_path_access_is_denied_by_default_and_valid_path_is_resolved(
    harness: Harness,
    tmp_path: Path,
) -> None:
    denied, denied_contexts = target_gateway(use_path=True)
    with pytest.raises(UnsafePathTarget, match="disabled"):
        execute_target(harness, denied, "reports/report.txt")
    assert denied_contexts == []

    root = tmp_path / "sandbox"
    root.mkdir()
    allowed, contexts = target_gateway(
        use_path=True,
        path_policy=PathPolicy(root),
    )
    execute_target(harness, allowed, "reports/report.txt")

    assert len(contexts) == 1
    assert contexts[0].normalized_path == str(
        (root / "reports" / "report.txt").resolve()
    )
    assert contexts[0].normalized_url is None


@pytest.mark.parametrize(
    "target",
    [
        "../secret.txt",
        "safe/../../secret.txt",
        "%2e%2e/secret.txt",
        "%252e%252e/secret.txt",
        "/etc/passwd",
        "C:\\Users\\owner\\secret.txt",
        "\\\\server\\share\\secret.txt",
    ],
)
def test_path_traversal_absolute_and_encoded_targets_stop_before_handler(
    harness: Harness,
    tmp_path: Path,
    target: str,
) -> None:
    root = tmp_path / "sandbox"
    root.mkdir()
    gateway, contexts = target_gateway(
        use_path=True,
        path_policy=PathPolicy(root),
    )

    with pytest.raises(UnsafePathTarget):
        execute_target(harness, gateway, target)

    assert contexts == []


def test_resolved_symlink_escape_stops_before_handler(
    harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "sandbox"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    resolved_root = root.resolve()
    escaped_candidate = (outside / "private.txt").resolve()
    original_resolve = Path.resolve

    def simulated_resolve(path: Path, strict: bool = False) -> Path:
        if path == root:
            return resolved_root
        if path == resolved_root / "escape" / "private.txt":
            return escaped_candidate
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", simulated_resolve)
    gateway, contexts = target_gateway(
        use_path=True,
        path_policy=PathPolicy(root),
    )

    with pytest.raises(UnsafePathTarget, match="escapes"):
        execute_target(harness, gateway, "escape/private.txt")

    assert contexts == []
