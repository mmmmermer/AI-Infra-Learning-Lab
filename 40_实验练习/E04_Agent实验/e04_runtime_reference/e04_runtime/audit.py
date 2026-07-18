from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from threading import RLock
from typing import Mapping

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
            sorted((key, self._redact(key, value)) for key, value in (details or {}).items())
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

    @staticmethod
    def _redact(key: str, value: object) -> str:
        lowered = key.lower()
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            return "[REDACTED]"
        text = str(value).replace("\r", " ").replace("\n", " ")
        return text[:160]

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)
