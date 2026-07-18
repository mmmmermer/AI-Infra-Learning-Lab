from __future__ import annotations

from dataclasses import dataclass

from redis import Redis
from redis.exceptions import ResponseError


@dataclass(frozen=True)
class QueueMessage:
    message_id: str
    task_id: str


class RedisTaskQueue:
    def __init__(
        self,
        url: str,
        key: str,
        *,
        group: str = "p03-workers",
        client: Redis | None = None,
    ) -> None:
        self.key = key
        self.group = group
        self.client = client or Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
        self._ensure_group()

    def _ensure_group(self) -> None:
        try:
            self.client.xgroup_create(
                name=self.key,
                groupname=self.group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def push(self, task_id: str) -> str:
        return str(self.client.xadd(self.key, {"task_id": task_id}))

    def receive(
        self,
        consumer_id: str,
        *,
        block_ms: int = 2_000,
        reclaim_idle_ms: int = 30_000,
    ) -> QueueMessage | None:
        reclaimed = self.client.xautoclaim(
            self.key,
            self.group,
            consumer_id,
            min_idle_time=reclaim_idle_ms,
            start_id="0-0",
            count=1,
        )
        reclaimed_messages = reclaimed[1] if len(reclaimed) > 1 else []
        if reclaimed_messages:
            return self._message(reclaimed_messages[0])

        streams = self.client.xreadgroup(
            self.group,
            consumer_id,
            {self.key: ">"},
            count=1,
            block=block_ms,
        )
        if not streams:
            return None
        return self._message(streams[0][1][0])

    def ack(self, message_id: str) -> None:
        acknowledged = int(self.client.xack(self.key, self.group, message_id))
        if acknowledged != 1:
            raise RuntimeError(f"queue acknowledgement failed for {message_id}")
        self.client.xdel(self.key, message_id)

    def length(self) -> int:
        groups = self.client.xinfo_groups(self.key)
        for group in groups:
            if group.get("name") == self.group:
                lag = group.get("lag")
                return int(group.get("pending", 0)) + (0 if lag is None else int(lag))
        return int(self.client.xlen(self.key))

    def ping(self) -> bool:
        return bool(self.client.ping())

    @staticmethod
    def _message(raw: tuple[str, dict[str, str]]) -> QueueMessage:
        message_id, fields = raw
        task_id = fields.get("task_id")
        if not task_id:
            raise RuntimeError(f"queue message {message_id} has no task_id")
        return QueueMessage(message_id=str(message_id), task_id=str(task_id))
