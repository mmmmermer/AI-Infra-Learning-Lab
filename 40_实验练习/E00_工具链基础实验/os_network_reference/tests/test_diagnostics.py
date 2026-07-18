from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import unittest

from diagnostics import (
    ProcessTopology,
    ensure_writable,
    render_diagnosis,
    run_child_process,
    run_signal_demo,
    trace_request_path,
)


REFERENCE_ROOT = Path(__file__).resolve().parents[1]
WORKER = REFERENCE_ROOT / "service_worker.py"


def successful_trace(status_code: int = 200):
    return trace_request_path(
        resolve=lambda: ["127.0.0.1"],
        connect=lambda addresses: {"peer": addresses[0]},
        handshake=lambda connection: {**connection, "tls": True},
        exchange_http=lambda _connection: status_code,
    )


def process_is_running(pid: int) -> bool:
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def write_delayed_worker(
    path: Path,
    *,
    delay_seconds: float,
    ready: bool,
    pid_path: Path,
    completion_path: Path,
) -> None:
    ready_statement = (
        'print(\'{"event": "ready"}\', flush=True)'
        if ready
        else "pass"
    )
    path.write_text(
        "\n".join(
            [
                "import os",
                "from pathlib import Path",
                "from time import sleep",
                f"Path({str(pid_path)!r}).write_text(str(os.getpid()))",
                f"sleep({delay_seconds!r})",
                ready_statement,
                f"Path({str(completion_path)!r}).write_text('completed')",
            ]
        ),
        encoding="utf-8",
    )


class RequestPathTests(unittest.TestCase):
    def test_success_observes_all_four_layers(self):
        result = successful_trace()

        self.assertTrue(result.ok)
        self.assertEqual(
            [observation.layer for observation in result.observations],
            ["dns", "tcp", "tls", "http"],
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(render_diagnosis(result))["failed_layer"], None)

    def test_dns_failure_stops_before_socket_creation(self):
        result = trace_request_path(
            resolve=lambda: (_ for _ in ()).throw(socket.gaierror("not found")),
            connect=lambda _addresses: self.fail("TCP must not run"),
            handshake=lambda _connection: self.fail("TLS must not run"),
            exchange_http=lambda _connection: self.fail("HTTP must not run"),
        )

        self.assertEqual(result.failed_layer, "dns")
        self.assertEqual(result.observations[-1].evidence, "gaierror")

    def test_tcp_failure_is_not_reported_as_http_500(self):
        result = trace_request_path(
            resolve=lambda: ["127.0.0.1"],
            connect=lambda _addresses: (_ for _ in ()).throw(
                ConnectionRefusedError("closed")
            ),
            handshake=lambda _connection: self.fail("TLS must not run"),
            exchange_http=lambda _connection: self.fail("HTTP must not run"),
        )

        self.assertEqual(result.failed_layer, "tcp")
        self.assertIsNone(result.status_code)

    def test_tls_failure_occurs_after_tcp_success(self):
        result = trace_request_path(
            resolve=lambda: ["127.0.0.1"],
            connect=lambda _addresses: object(),
            handshake=lambda _connection: (_ for _ in ()).throw(
                ssl.SSLError("certificate verify failed")
            ),
            exchange_http=lambda _connection: self.fail("HTTP must not run"),
        )

        self.assertEqual(result.failed_layer, "tls")
        self.assertEqual(
            [(item.layer, item.outcome) for item in result.observations],
            [("dns", "ok"), ("tcp", "ok"), ("tls", "failed")],
        )

    def test_http_500_proves_the_lower_layers_were_reached(self):
        result = successful_trace(status_code=500)

        self.assertEqual(result.failed_layer, "http")
        self.assertEqual(result.status_code, 500)
        self.assertEqual(len(result.observations), 4)


class ProcessAndPermissionTests(unittest.TestCase):
    def test_exit_code_pid_parent_and_environment_are_observable(self):
        result = run_child_process(
            [sys.executable, str(WORKER), "--exit-code", "7"],
            env_overrides={"DEMO_MODE": "test"},
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.exit_code, 7)
        topology = result.classify_worker(
            worker_pid=payload["pid"],
            worker_parent_pid=payload["parent_pid"],
        )
        if topology is ProcessTopology.DIRECT_CHILD:
            self.assertEqual(payload["pid"], result.launcher_pid)
            self.assertEqual(payload["parent_pid"], result.caller_pid)
        else:
            self.assertIs(topology, ProcessTopology.WINDOWS_VENV_REDIRECTOR)
            self.assertTrue(result.windows_venv_redirector_expected)
            self.assertNotEqual(payload["pid"], result.launcher_pid)
            self.assertEqual(payload["parent_pid"], result.launcher_pid)
        self.assertEqual(payload["demo_mode"], "test")

    def test_permission_failure_is_detected_before_write_and_can_recover(self):
        target = REFERENCE_ROOT / "artifacts" / "result.json"

        with self.assertRaises(PermissionError):
            ensure_writable(target, access_check=lambda _path, _mode: False)
        self.assertEqual(
            ensure_writable(target, access_check=lambda _path, _mode: True),
            target,
        )

    def test_child_timeout_kills_reaps_and_prevents_late_side_effect(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            pid_path = root / "worker.pid"
            completion_path = root / "completed.txt"
            code = (
                "import os, time; from pathlib import Path; "
                f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
                "time.sleep(5); "
                f"Path({str(completion_path)!r}).write_text('completed')"
            )

            with self.assertRaises(subprocess.TimeoutExpired):
                run_child_process([sys.executable, "-c", code], timeout=1.0)

            worker_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertFalse(completion_path.exists())
            self.assertFalse(process_is_running(worker_pid))

    def test_service_catches_shutdown_signal_and_cleans_up(self):
        result = run_signal_demo(WORKER)

        self.assertEqual(result.exit_code, 0)
        events = [json.loads(line)["event"] for line in result.stdout.splitlines()]
        self.assertEqual(events, ["ready", "signal", "cleanup"])

    def test_signal_demo_silent_startup_is_bounded_and_reaped(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            worker = root / "silent_worker.py"
            pid_path = root / "worker.pid"
            completion_path = root / "completed.txt"
            write_delayed_worker(
                worker,
                delay_seconds=5.0,
                ready=False,
                pid_path=pid_path,
                completion_path=completion_path,
            )

            started_at = perf_counter()
            with self.assertRaises(subprocess.TimeoutExpired):
                run_signal_demo(worker, timeout=1.0)
            elapsed = perf_counter() - started_at

            worker_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertLess(elapsed, 2.5)
            self.assertFalse(completion_path.exists())
            self.assertFalse(process_is_running(worker_pid))

    def test_signal_demo_late_ready_is_bounded_and_reaped(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            worker = root / "late_ready_worker.py"
            pid_path = root / "worker.pid"
            completion_path = root / "completed.txt"
            write_delayed_worker(
                worker,
                delay_seconds=5.0,
                ready=True,
                pid_path=pid_path,
                completion_path=completion_path,
            )

            started_at = perf_counter()
            with self.assertRaises(subprocess.TimeoutExpired):
                run_signal_demo(worker, timeout=1.0)
            elapsed = perf_counter() - started_at

            worker_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertLess(elapsed, 2.5)
            self.assertFalse(completion_path.exists())
            self.assertFalse(process_is_running(worker_pid))


if __name__ == "__main__":
    unittest.main()
