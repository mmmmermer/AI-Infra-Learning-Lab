from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_ms: int = 0


class FixedWindowRateLimiter:
    def __init__(
        self,
        *,
        capacity: int = 100,
        window_seconds: float = 1.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if capacity < 1 or window_seconds <= 0:
            raise ValueError("capacity and window_seconds must be positive")
        self._capacity = capacity
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = RLock()

    def consume(self, key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            started_at, count = self._windows.get(key, (now, 0))
            elapsed = now - started_at
            if elapsed >= self._window_seconds:
                started_at, count = now, 0
                elapsed = 0.0
            if count >= self._capacity:
                retry_ms = max(1, int((self._window_seconds - elapsed) * 1000))
                return RateLimitDecision(False, retry_ms)
            self._windows[key] = (started_at, count + 1)
            return RateLimitDecision(True)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
