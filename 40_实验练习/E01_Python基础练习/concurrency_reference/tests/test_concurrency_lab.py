from __future__ import annotations

import asyncio
from threading import Event as ThreadEvent
import unittest

from concurrency_lab import (
    ResourceProbe,
    WorkloadKind,
    benchmark_blocking_io,
    cancel_and_join,
    choose_concurrency_model,
    cpu_checksum,
    loop_progresses_during_direct_call,
    loop_progresses_while_call_is_offloaded,
    run_cpu_processes,
    time_out_and_join,
)


class SelectionAndExecutorTests(unittest.TestCase):
    def test_thread_process_and_asyncio_choices_have_distinct_reasons(self):
        decisions = {
            kind: choose_concurrency_model(kind)
            for kind in WorkloadKind
        }

        self.assertEqual(decisions[WorkloadKind.BLOCKING_IO].model, "thread")
        self.assertEqual(decisions[WorkloadKind.CPU_BOUND].model, "process")
        self.assertEqual(decisions[WorkloadKind.ASYNC_IO].model, "asyncio")
        self.assertEqual(len({decision.reason for decision in decisions.values()}), 3)

    def test_threads_overlap_blocking_io_without_changing_result_order(self):
        benchmark = benchmark_blocking_io(
            ["a", "b", "c", "d"],
            delay_seconds=0.03,
            max_workers=4,
        )

        self.assertEqual(benchmark.sequential_results, ("A", "B", "C", "D"))
        self.assertEqual(benchmark.threaded_results, benchmark.sequential_results)
        self.assertLess(benchmark.threaded_seconds, benchmark.sequential_seconds)

    def test_process_pool_matches_the_same_cpu_function(self):
        limits = (2_000, 2_500)

        self.assertEqual(
            run_cpu_processes(limits),
            tuple(cpu_checksum(limit) for limit in limits),
        )


class AsyncCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_call_blocks_loop_progress_but_to_thread_allows_it(self):
        blocked_progress = await loop_progresses_during_direct_call(lambda: None)
        offloaded_progress = await loop_progresses_while_call_is_offloaded(
            lambda: None
        )

        self.assertFalse(blocked_progress)
        self.assertTrue(offloaded_progress)

        call_started = asyncio.Event()
        release_call = ThreadEvent()
        loop = asyncio.get_running_loop()

        def controlled_call() -> None:
            loop.call_soon_threadsafe(call_started.set)
            release_call.wait()

        helper = asyncio.create_task(
            loop_progresses_while_call_is_offloaded(controlled_call)
        )
        await call_started.wait()
        helper.cancel()
        await asyncio.sleep(0)
        cancellation_waited_for_worker = not helper.done()
        release_call.set()

        with self.assertRaises(asyncio.CancelledError):
            await helper
        self.assertTrue(cancellation_waited_for_worker)

    async def test_explicit_cancellation_is_awaited_and_releases_resource(self):
        probe = ResourceProbe()

        cancelled = await cancel_and_join(probe)

        self.assertTrue(cancelled)
        self.assertEqual((probe.acquired, probe.released), (1, 1))

    async def test_timeout_cancels_child_and_releases_resource(self):
        probe = ResourceProbe()

        started = await time_out_and_join(probe, timeout_seconds=0.01)

        self.assertTrue(started)
        self.assertEqual((probe.acquired, probe.released), (1, 1))


if __name__ == "__main__":
    unittest.main()
