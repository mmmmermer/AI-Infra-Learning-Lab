from app.redis_queue import RedisTaskQueue


class FakeRedis:
    def __init__(self) -> None:
        self.reclaimed = []
        self.new_messages = []
        self.acked = []
        self.deleted = []
        self.added = []
        self.groups = [{"name": "p03-workers", "pending": 0, "lag": 0}]

    def xgroup_create(self, **kwargs):
        return True

    def xadd(self, key, fields):
        self.added.append((key, fields))
        return "1-0"

    def xautoclaim(self, *args, **kwargs):
        return ["0-0", self.reclaimed, []]

    def xreadgroup(self, *args, **kwargs):
        if not self.new_messages:
            return []
        return [("p03:tasks:stream:v1", self.new_messages)]

    def xack(self, key, group, message_id):
        self.acked.append((key, group, message_id))
        return 1

    def xdel(self, key, message_id):
        self.deleted.append((key, message_id))
        return 1

    def xinfo_groups(self, key):
        return self.groups

    def xlen(self, key):
        return 0

    def ping(self):
        return True


def queue_with(fake: FakeRedis) -> RedisTaskQueue:
    return RedisTaskQueue(
        "redis://unused",
        "p03:tasks:stream:v1",
        client=fake,
    )


def test_pending_message_is_reclaimed_before_new_delivery():
    fake = FakeRedis()
    fake.reclaimed = [("7-0", {"task_id": "task-recovered"})]
    fake.new_messages = [("8-0", {"task_id": "task-new"})]

    message = queue_with(fake).receive("worker-2", reclaim_idle_ms=1)

    assert message.message_id == "7-0"
    assert message.task_id == "task-recovered"


def test_new_message_is_acknowledged_only_by_explicit_ack():
    fake = FakeRedis()
    fake.new_messages = [("8-0", {"task_id": "task-new"})]
    queue = queue_with(fake)

    message = queue.receive("worker-1")
    assert fake.acked == []

    queue.ack(message.message_id)
    assert fake.acked == [("p03:tasks:stream:v1", "p03-workers", "8-0")]
    assert fake.deleted == [("p03:tasks:stream:v1", "8-0")]


def test_backlog_counts_pending_and_undelivered_messages():
    fake = FakeRedis()
    fake.groups = [{"name": "p03-workers", "pending": 2, "lag": 3}]

    assert queue_with(fake).length() == 5


def test_publish_uses_stream_entry():
    fake = FakeRedis()
    queue = queue_with(fake)

    assert queue.push("task-1") == "1-0"
    assert fake.added == [
        ("p03:tasks:stream:v1", {"task_id": "task-1"})
    ]
