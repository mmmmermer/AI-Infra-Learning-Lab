from __future__ import annotations

from .postgres_store import PostgresTaskStore
from .redis_queue import RedisTaskQueue
from .settings import Settings


def main() -> None:
    settings = Settings.from_env()
    if settings.backend != "postgres":
        return
    if not PostgresTaskStore(settings.database_url).ping():
        raise SystemExit(1)
    if not RedisTaskQueue(settings.redis_url, settings.redis_queue_key).ping():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
