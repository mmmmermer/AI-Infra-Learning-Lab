from __future__ import annotations

import logging
import os
import socket
from time import sleep

from .postgres_store import PostgresTaskStore
from .redis_queue import RedisTaskQueue
from .settings import Settings


LOGGER = logging.getLogger("p03.dispatcher")


def run_forever() -> None:
    settings = Settings.from_env()
    if settings.backend != "postgres":
        raise RuntimeError("dispatcher requires P03_BACKEND=postgres")

    store = PostgresTaskStore(settings.database_url)
    queue = RedisTaskQueue(settings.redis_url, settings.redis_queue_key)
    dispatcher_id = f"{socket.gethostname()}:{os.getpid()}"

    while True:
        try:
            events = store.claim_outbox(
                dispatcher_id,
                settings.outbox_batch_size,
                settings.outbox_claim_seconds,
            )
        except Exception:
            LOGGER.exception("outbox claim failed")
            sleep(1)
            continue

        if not events:
            sleep(0.2)
            continue

        for event in events:
            try:
                queue.push(str(event["task_id"]))
            except Exception:
                LOGGER.exception("redis publish failed for event_id=%s", event["event_id"])
                try:
                    store.release_outbox_claim(int(event["event_id"]), dispatcher_id)
                except Exception:
                    LOGGER.exception("outbox claim release failed")
                continue

            try:
                store.mark_outbox_published(int(event["event_id"]), dispatcher_id)
            except Exception:
                # The Redis write may already be visible. The claim lease permits a
                # later duplicate delivery, which the worker's task CAS will reject.
                LOGGER.exception("outbox acknowledgement failed for event_id=%s", event["event_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
