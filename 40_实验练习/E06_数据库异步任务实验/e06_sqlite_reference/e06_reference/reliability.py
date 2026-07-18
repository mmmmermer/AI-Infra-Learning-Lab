from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import math
from typing import Iterable


class DeliverySemantics(StrEnum):
    AT_MOST_ONCE = "at-most-once"
    AT_LEAST_ONCE = "at-least-once"
    EFFECTIVELY_ONCE = "effectively-once"


class CrashPoint(StrEnum):
    BEFORE_RECEIVE = "before-receive"
    AFTER_RECEIVE_BEFORE_EFFECT = "after-receive-before-effect"
    AFTER_EFFECT_BEFORE_FINALIZE = "after-effect-before-finalize"
    AFTER_FINALIZE_BEFORE_ACK = "after-finalize-before-ack"
    AFTER_ACK = "after-ack"


@dataclass(frozen=True)
class CrashOutcome:
    redelivery_expected: bool
    effect_count: int
    eventual_status: str
    lost_or_inconsistent: bool
    duplicate_effect: bool


def derive_crash_outcome(
    semantics: DeliverySemantics,
    crash_point: CrashPoint,
) -> CrashOutcome:
    """Derive the eventual observable result for one crash and one recovery."""
    if crash_point in (CrashPoint.BEFORE_RECEIVE, CrashPoint.AFTER_ACK):
        return CrashOutcome(
            redelivery_expected=crash_point == CrashPoint.BEFORE_RECEIVE,
            effect_count=1,
            eventual_status="succeeded",
            lost_or_inconsistent=False,
            duplicate_effect=False,
        )

    if semantics == DeliverySemantics.AT_MOST_ONCE:
        if crash_point == CrashPoint.AFTER_RECEIVE_BEFORE_EFFECT:
            return CrashOutcome(False, 0, "lost", True, False)
        if crash_point == CrashPoint.AFTER_EFFECT_BEFORE_FINALIZE:
            return CrashOutcome(False, 1, "running", True, False)
        return CrashOutcome(False, 1, "succeeded", False, False)

    duplicate_effect = (
        semantics == DeliverySemantics.AT_LEAST_ONCE
        and crash_point
        in (
            CrashPoint.AFTER_EFFECT_BEFORE_FINALIZE,
            CrashPoint.AFTER_FINALIZE_BEFORE_ACK,
        )
    )
    return CrashOutcome(
        redelivery_expected=True,
        effect_count=2 if duplicate_effect else 1,
        eventual_status="succeeded",
        lost_or_inconsistent=False,
        duplicate_effect=duplicate_effect,
    )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.25

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be positive")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be at least base_delay_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


def retry_delay_seconds(
    task_key: str,
    attempt: int,
    policy: RetryPolicy,
    *,
    jitter: bool = True,
) -> float:
    if not 1 <= attempt <= policy.max_attempts:
        raise ValueError("attempt is outside the bounded retry policy")

    exponential = min(
        policy.max_delay_seconds,
        policy.base_delay_seconds * (2 ** (attempt - 1)),
    )
    if not jitter or policy.jitter_ratio == 0:
        return exponential

    digest = sha256(f"{task_key}:{attempt}".encode("utf-8")).digest()
    unit_interval = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    factor = 1 - policy.jitter_ratio + (2 * policy.jitter_ratio * unit_interval)
    return min(policy.max_delay_seconds, exponential * factor)


def build_retry_schedule(
    task_keys: Iterable[str],
    policy: RetryPolicy,
    *,
    jitter: bool = True,
) -> dict[str, tuple[float, ...]]:
    schedule: dict[str, tuple[float, ...]] = {}
    for task_key in task_keys:
        elapsed = 0.0
        due_times: list[float] = []
        for attempt in range(1, policy.max_attempts + 1):
            elapsed += retry_delay_seconds(
                task_key,
                attempt,
                policy,
                jitter=jitter,
            )
            due_times.append(elapsed)
        schedule[task_key] = tuple(due_times)
    return schedule


def peak_retry_load(
    schedule: dict[str, tuple[float, ...]],
    *,
    bucket_seconds: float = 0.25,
) -> int:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    buckets: dict[int, int] = {}
    for due_times in schedule.values():
        for due_time in due_times:
            bucket = math.floor(due_time / bucket_seconds)
            buckets[bucket] = buckets.get(bucket, 0) + 1
    return max(buckets.values(), default=0)
