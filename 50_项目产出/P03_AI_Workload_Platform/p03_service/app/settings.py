from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    backend: str
    database_url: str
    redis_url: str
    redis_queue_key: str
    outbox_batch_size: int
    outbox_claim_seconds: int
    worker_lease_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.getenv("P03_BACKEND", "memory").strip().lower()
        if backend not in {"memory", "postgres"}:
            raise ValueError("P03_BACKEND must be 'memory' or 'postgres'")
        return cls(
            backend=backend,
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://p03:p03@db:5432/p03"
            ),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            redis_queue_key=os.getenv("REDIS_QUEUE_KEY", "p03:tasks:stream:v1"),
            outbox_batch_size=int(os.getenv("OUTBOX_BATCH_SIZE", "20")),
            outbox_claim_seconds=int(os.getenv("OUTBOX_CLAIM_SECONDS", "15")),
            worker_lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "30")),
        )
