from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from threading import Event as ThreadEvent
from time import perf_counter, sleep
from typing import Callable, Sequence, TypeVar


T = TypeVar("T")


class WorkloadKind(StrEnum):
    BLOCKING_IO = "blocking_io"
    CPU_BOUND = "cpu_bound"
    ASYNC_IO = "async_io"


@dataclass(frozen=True)
class ConcurrencyDecision:
    model: str
    reason: str


@dataclass(frozen=True)
class IOBenchmark:
    sequential_seconds: float
    threaded_seconds: float
    sequential_results: tuple[str, ...]
    threaded_results: tuple[str, ...]


@dataclass
class ResourceProbe:
    acquired: int = 0
    released: int = 0


def choose_concurrency_model(kind: WorkloadKind) -> ConcurrencyDecision:
    if kind is WorkloadKind.BLOCKING_IO:
        return ConcurrencyDecision(
            "thread",
            "Threads let blocking file or legacy network calls overlap while sharing memory.",
        )
    if kind is WorkloadKind.CPU_BOUND:
        return ConcurrencyDecision(
            "process",
            "Processes isolate CPU-bound Python work from the interpreter lock.",
        )
    return ConcurrencyDecision(
        "asyncio",
        "Asyncio scales many cooperative waits when every blocking boundary is awaitable.",
    )


def _blocking_io(item: str, delay_seconds: float) -> str:
    sleep(delay_seconds)
    return item.upper()


def benchmark_blocking_io(
    items: Sequence[str],
    *,
    delay_seconds: float = 0.02,
    max_workers: int = 4,
) -> IOBenchmark:
    sequential_started = perf_counter()
    sequential = tuple(_blocking_io(item, delay_seconds) for item in items)
    sequential_seconds = perf_counter() - sequential_started

    threaded_started = perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        threaded = tuple(
            executor.map(_blocking_io, items, [delay_seconds] * len(items))
        )
    threaded_seconds = perf_counter() - threaded_started
    return IOBenchmark(
        sequential_seconds,
        threaded_seconds,
        sequential,
        threaded,
    )


def cpu_checksum(limit: int) -> int:
    return sum(value * value for value in range(limit))


def run_cpu_processes(limits: Sequence[int], *, max_workers: int = 2) -> tuple[int, ...]:
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return tuple(executor.map(cpu_checksum, limits))


async def loop_progresses_during_direct_call(
    blocking_call: Callable[[], T],
) -> bool:
    loop = asyncio.get_running_loop()
    loop_progressed = asyncio.Event()
    loop.call_soon(loop_progressed.set)

    blocking_call()
    progressed_before_return = loop_progressed.is_set()

    await loop_progressed.wait()
    return progressed_before_return


async def loop_progresses_while_call_is_offloaded(
    blocking_call: Callable[[], T],
) -> bool:
    loop = asyncio.get_running_loop()
    worker_started = asyncio.Event()
    release_worker = ThreadEvent()
    loop_progressed = asyncio.Event()

    def gated_call() -> T:
        loop.call_soon_threadsafe(worker_started.set)
        release_worker.wait()
        return blocking_call()

    worker = asyncio.create_task(asyncio.to_thread(gated_call))
    try:
        await worker_started.wait()
        loop.call_soon(loop_progressed.set)
        await loop_progressed.wait()
        return not release_worker.is_set() and not worker.done()
    finally:
        release_worker.set()
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            finally:
                raise


async def wait_with_resource(probe: ResourceProbe, started: asyncio.Event) -> None:
    probe.acquired += 1
    started.set()
    try:
        await asyncio.Event().wait()
    finally:
        probe.released += 1


async def cancel_and_join(probe: ResourceProbe) -> bool:
    started = asyncio.Event()
    task = asyncio.create_task(wait_with_resource(probe, started))
    await started.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return task.cancelled()


async def time_out_and_join(probe: ResourceProbe, *, timeout_seconds: float) -> bool:
    started = asyncio.Event()
    try:
        async with asyncio.timeout(timeout_seconds):
            await wait_with_resource(probe, started)
    except TimeoutError:
        return started.is_set()
    return False
