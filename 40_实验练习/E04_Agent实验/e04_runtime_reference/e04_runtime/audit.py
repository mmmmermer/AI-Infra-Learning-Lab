from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from threading import RLock

from .models import Principal


SENSITIVE_KEY_PARTS = (
    "authorization",
    "token",
    "secret",
    "password",
    "query",
    "prompt",
    "chunk",
    "draft",
    "content",
    "message",
    "comment",
    "owner_user_id",
    "user_id",
    "cookie",
    "header",
    "body",
    "payload",
    "output",
    "observation",
    "response",
    "url",
    "uri",
    "path",
    "reason",
)
SAFE_BOOLEAN_METADATA_KEYS = frozenset(
    {
        "approval_note_present",
        "reason_present",
    }
)
SAFE_INTEGER_METADATA_KEYS = frozenset(
    {
        "approval_note_length",
        "query_length",
        "reason_length",
        "source_count",
        "step_number",
        "version",
    }
)
SAFE_HASH_METADATA_KEYS = frozenset(
    {
        "action_sha256",
        "draft_sha256",
        "query_hash",
    }
)
SAFE_METADATA_KEYS = (
    SAFE_BOOLEAN_METADATA_KEYS
    | SAFE_INTEGER_METADATA_KEYS
    | SAFE_HASH_METADATA_KEYS
)
_METADATA_SUFFIXES = ("_count", "_hash", "_length", "_present", "_sha256")
_SAFE_HASH_PATTERN = re.compile(r"^(?:[0-9a-f]{16}|[0-9a-f]{64})$")

_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;\"']+")
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b"
    r"\s*[:=]\s*[^\s,;\"']+"
)
_URL_PATTERN = re.compile(r"(?i)\bhttps?://[^\s\"']+")
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?:[a-z]:\\|\\\\)[^\s\"']+")
_POSIX_PRIVATE_PATH_PATTERN = re.compile(
    r"/(?:home|users|etc|var|tmp|root)/[^\s\"']+",
    re.IGNORECASE,
)


def stable_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    sequence: int
    occurred_at: datetime
    event_type: str
    tenant_hash: str
    subject_hash: str
    details: tuple[tuple[str, str], ...]


class RedactedAuditLog:
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = RLock()

    def append(
        self,
        *,
        occurred_at: datetime,
        event_type: str,
        principal: Principal,
        details: Mapping[str, object] | None = None,
    ) -> AuditRecord:
        safe_details = tuple(
            sorted(
                (str(key)[:64], self._redact(str(key), value))
                for key, value in (details or {}).items()
            )
        )
        with self._lock:
            record = AuditRecord(
                sequence=len(self._records) + 1,
                occurred_at=occurred_at,
                event_type=event_type,
                tenant_hash=stable_hash(principal.tenant_id),
                subject_hash=stable_hash(principal.owner_user_id),
                details=safe_details,
            )
            self._records.append(record)
            return record

    @classmethod
    def _redact(cls, key: str, value: object) -> str:
        lowered = key.lower()
        if lowered in SAFE_METADATA_KEYS:
            if not cls._is_valid_safe_metadata(lowered, value):
                return "[REDACTED]"
        elif cls._is_sensitive_key(lowered) or lowered.endswith(_METADATA_SUFFIXES):
            return "[REDACTED]"
        sanitized = cls._sanitize_nested(value, depth=0)
        if isinstance(sanitized, (dict, list)):
            text = json.dumps(
                sanitized,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        else:
            text = str(sanitized)
        text = text.replace("\r", " ").replace("\n", " ")
        for pattern, replacement in (
            (_BEARER_PATTERN, "[REDACTED_CREDENTIAL]"),
            (_NAMED_SECRET_PATTERN, "[REDACTED_CREDENTIAL]"),
            (_URL_PATTERN, "[REDACTED_URL]"),
            (_WINDOWS_PATH_PATTERN, "[REDACTED_PATH]"),
            (_POSIX_PRIVATE_PATH_PATTERN, "[REDACTED_PATH]"),
        ):
            text = pattern.sub(replacement, text)
        return text[:160]

    @classmethod
    def _sanitize_nested(cls, value: object, *, depth: int) -> object:
        if depth >= 6:
            return "[REDACTED_DEPTH]"
        if isinstance(value, Mapping):
            result: dict[str, object] = {}
            redacted_field_count = 0
            for raw_key, nested_value in value.items():
                key = str(raw_key)[:64]
                lowered = key.lower()
                if cls._is_valid_safe_metadata(lowered, nested_value):
                    result[key] = nested_value
                    continue
                redacted_field_count += 1
            if redacted_field_count:
                result["redacted_field_count"] = redacted_field_count
            return result
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return "[REDACTED_SEQUENCE]"
        if isinstance(value, (set, frozenset)):
            return "[REDACTED_SEQUENCE]"
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _is_sensitive_key(lowered_key: str) -> bool:
        return any(part in lowered_key for part in SENSITIVE_KEY_PARTS)

    @staticmethod
    def _is_valid_safe_metadata(lowered_key: str, value: object) -> bool:
        if lowered_key in SAFE_BOOLEAN_METADATA_KEYS:
            return isinstance(value, bool)
        if lowered_key in SAFE_INTEGER_METADATA_KEYS:
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            )
        if lowered_key in SAFE_HASH_METADATA_KEYS:
            return (
                isinstance(value, str)
                and _SAFE_HASH_PATTERN.fullmatch(value) is not None
            )
        return False

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)
