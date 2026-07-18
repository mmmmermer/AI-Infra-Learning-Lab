from __future__ import annotations

import logging
import os
import socket
from time import monotonic

from .postgres_store import PostgresTaskStore
from .redis_queue import RedisTaskQueue
from .settings import Settings
from .worker import execute_task


LOGGER = logging.getLogger("p03.worker")


def run_forever() -> None:
    settings = Settings.from_env()
    if settings.backend != "postgres":
        raise RuntimeError("worker service requires P03_BACKEND=postgres")

    store = PostgresTaskStore(settings.database_url)
    queue = RedisTaskQueue(settings.redis_url, settings.redis_queue_key)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    last_reconciliation = 0.0

    while True:
        current = monotonic()
        if current - last_reconciliation >= 5:
            try:
                recovered = store.reconcile_expired_leases()
                if recovered:
                    LOGGER.warning("reconciled %s expired task lease(s)", recovered)
            except Exception:
                LOGGER.exception("lease reconciliation failed")
            last_reconciliation = current

        try:
            message = queue.receive(
                worker_id,
                block_ms=2_000,
                reclaim_idle_ms=settings.worker_lease_seconds * 1_000,
            )
        except Exception:
            LOGGER.exception("redis receive failed")
            continue
        if message is None:
            continue
        task_id = message.task_id

        try:
            task = store.claim_task(task_id, worker_id, settings.worker_lease_seconds)
        except Exception:
            LOGGER.exception("task claim failed task_id=%s", task_id)
            queue.push(task_id)
            continue
        if task is None:
            LOGGER.info("ignored duplicate or stale delivery task_id=%s", task_id)
            queue.ack(message.message_id)
            continue

        execution = execute_task(task)
        try:
            if execution.error_type is not None:
                store.fail(
                    task.task_id,
                    worker_id,
                    task.version,
                    execution.error_type,
                    execution.runtime_ms,
                )
            else:
                assert execution.result_json is not None
                store.succeed(
                    task.task_id,
                    worker_id,
                    task.version,
                    execution.result_json,
                    execution.runtime_ms,
                )
            queue.ack(message.message_id)
        except Exception:
            LOGGER.exception("task finalization failed task_id=%s", task.task_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
