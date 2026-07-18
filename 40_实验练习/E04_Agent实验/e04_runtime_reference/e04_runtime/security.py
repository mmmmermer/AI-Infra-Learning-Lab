from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit, urlunsplit

from .errors import UnsafeEgressTarget, UnsafePathTarget


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.azure.internal",
        "instance-data",
    }
)
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")


def _normalized_host(raw_host: str) -> str:
    if raw_host.endswith("."):
        raise UnsafeEgressTarget("trailing-dot hostnames are not allowed")
    try:
        host = raw_host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeEgressTarget("hostname is not valid IDNA") from exc
    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise UnsafeEgressTarget("local or metadata hostnames are not allowed")

    try:
        address = ip_address(host)
    except ValueError:
        labels = host.split(".")
        if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise UnsafeEgressTarget("hostname is not a canonical public DNS name")
        if all(label.isdigit() for label in labels) or any(
            label.startswith("0x") for label in labels
        ):
            raise UnsafeEgressTarget("non-canonical numeric hosts are not allowed")
    else:
        if not address.is_global:
            raise UnsafeEgressTarget("non-global IP addresses are not allowed")
        host = address.compressed
    return host


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    """Exact-origin allowlist. An empty allowlist denies every network target."""

    allowed_origins: frozenset[tuple[str, str, int]] = frozenset()

    def validate(self, raw_url: str) -> str:
        if not self.allowed_origins:
            raise UnsafeEgressTarget("network egress is disabled")
        if not isinstance(raw_url, str) or not raw_url or len(raw_url) > 2048:
            raise UnsafeEgressTarget("URL length is invalid")
        if "\\" in raw_url or any(
            ord(character) <= 32 or ord(character) == 127 for character in raw_url
        ):
            raise UnsafeEgressTarget("URL contains ambiguous characters")

        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except ValueError as exc:
            raise UnsafeEgressTarget("URL authority is invalid") from exc
        if (
            not parsed.scheme
            or not parsed.netloc
            or parsed.hostname is None
            or port is None
        ):
            raise UnsafeEgressTarget("URL must include an explicit scheme, host, and port")
        if not 1 <= port <= 65535:
            raise UnsafeEgressTarget("URL port is outside the valid range")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeEgressTarget("userinfo is not allowed in URLs")
        if "%" in parsed.netloc or parsed.fragment:
            raise UnsafeEgressTarget("encoded authorities and fragments are not allowed")

        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise UnsafeEgressTarget("only HTTP(S) egress can be allowlisted")
        host = _normalized_host(parsed.hostname)
        allowed = {
            (allowed_scheme.lower(), _normalized_host(allowed_host), allowed_port)
            for allowed_scheme, allowed_host, allowed_port in self.allowed_origins
        }
        if (scheme, host, port) not in allowed:
            raise UnsafeEgressTarget("origin is not allowlisted")

        authority_host = f"[{host}]" if ":" in host else host
        return urlunsplit(
            (
                scheme,
                f"{authority_host}:{port}",
                parsed.path or "/",
                parsed.query,
                "",
            )
        )


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Resolve one relative path beneath one configured root; no root means deny."""

    root: Path | None = None

    def validate(self, raw_path: str) -> str:
        if self.root is None:
            raise UnsafePathTarget("filesystem access is disabled")
        if not isinstance(raw_path, str) or not raw_path or len(raw_path) > 1024:
            raise UnsafePathTarget("path length is invalid")
        if any(ord(character) <= 31 or ord(character) == 127 for character in raw_path):
            raise UnsafePathTarget("path contains control characters")
        if unquote(raw_path) != raw_path:
            raise UnsafePathTarget("percent-encoded paths are not accepted")

        windows_path = PureWindowsPath(raw_path)
        posix_path = PurePosixPath(raw_path.replace("\\", "/"))
        if windows_path.is_absolute() or windows_path.drive or posix_path.is_absolute():
            raise UnsafePathTarget("absolute, drive, and UNC paths are not accepted")
        parts = posix_path.parts
        if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
            raise UnsafePathTarget("path contains traversal or ambiguous segments")

        try:
            root = Path(self.root).resolve(strict=True)
            candidate = root.joinpath(*parts).resolve(strict=False)
            candidate.relative_to(root)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise UnsafePathTarget("path escapes the configured root") from exc
        return str(candidate)
