from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
from time import monotonic


@dataclass(frozen=True)
class StageObservation:
    layer: str
    outcome: str
    evidence: str


@dataclass(frozen=True)
class RequestDiagnosis:
    ok: bool
    failed_layer: str | None
    status_code: int | None
    observations: tuple[StageObservation, ...]


class ProcessTopology(StrEnum):
    DIRECT_CHILD = "direct_child"
    WINDOWS_VENV_REDIRECTOR = "windows_venv_redirector"


@dataclass(frozen=True)
class ProcessObservation:
    launcher_pid: int
    caller_pid: int
    exit_code: int
    stdout: str
    stderr: str
    windows_venv_redirector_expected: bool

    def classify_worker(
        self,
        *,
        worker_pid: int,
        worker_parent_pid: int,
    ) -> ProcessTopology:
        if worker_pid == self.launcher_pid and worker_parent_pid == self.caller_pid:
            return ProcessTopology.DIRECT_CHILD
        if (
            self.windows_venv_redirector_expected
            and worker_pid != self.launcher_pid
            and worker_parent_pid == self.launcher_pid
        ):
            return ProcessTopology.WINDOWS_VENV_REDIRECTOR
        raise ValueError(
            "worker PID/PPID does not match a direct child or the expected "
            "Windows virtual-environment redirector topology"
        )


def trace_request_path(
    *,
    resolve: Callable[[], object],
    connect: Callable[[object], object],
    handshake: Callable[[object], object],
    exchange_http: Callable[[object], int],
) -> RequestDiagnosis:
    observations: list[StageObservation] = []
    try:
        addresses = resolve()
        observations.append(StageObservation("dns", "ok", "address_resolved"))
    except (socket.gaierror, OSError) as exc:
        return _failure("dns", exc, observations)

    try:
        connection = connect(addresses)
        observations.append(StageObservation("tcp", "ok", "connection_established"))
    except (ConnectionError, TimeoutError, OSError) as exc:
        return _failure("tcp", exc, observations)

    try:
        secure_connection = handshake(connection)
        observations.append(StageObservation("tls", "ok", "handshake_completed"))
    except (ssl.SSLError, TimeoutError, OSError) as exc:
        return _failure("tls", exc, observations)

    try:
        status_code = exchange_http(secure_connection)
    except (TimeoutError, OSError) as exc:
        return _failure("http", exc, observations)
    if not 100 <= status_code <= 599:
        raise ValueError("HTTP status must be between 100 and 599")
    if status_code >= 400:
        observations.append(
            StageObservation("http", "failed", f"status_code={status_code}")
        )
        return RequestDiagnosis(False, "http", status_code, tuple(observations))

    observations.append(StageObservation("http", "ok", f"status_code={status_code}"))
    return RequestDiagnosis(True, None, status_code, tuple(observations))


def _failure(
    layer: str,
    error: Exception,
    observations: list[StageObservation],
) -> RequestDiagnosis:
    observations.append(
        StageObservation(layer, "failed", type(error).__name__)
    )
    return RequestDiagnosis(False, layer, None, tuple(observations))


def render_diagnosis(diagnosis: RequestDiagnosis) -> str:
    return json.dumps(asdict(diagnosis), ensure_ascii=True, sort_keys=True)


def ensure_writable(
    path: Path,
    *,
    access_check: Callable[[Path, int], bool] = os.access,
) -> Path:
    target = path if path.exists() else path.parent
    if not access_check(target, os.W_OK):
        raise PermissionError(f"write permission denied for {target}")
    return path


def run_child_process(
    command: Sequence[str],
    *,
    env_overrides: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> ProcessObservation:
    argv = list(command)
    if not argv:
        raise ValueError("command must contain an executable")
    environment = os.environ.copy()
    environment.update(env_overrides or {})
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_and_reap(process)
        raise
    return ProcessObservation(
        launcher_pid=process.pid,
        caller_pid=os.getpid(),
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        windows_venv_redirector_expected=_is_windows_venv_launcher(argv[0]),
    )


def _is_windows_venv_launcher(executable: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        executable_path = Path(executable).resolve(strict=True)
    except OSError:
        return False
    return (
        executable_path.name.casefold() in {"python.exe", "pythonw.exe"}
        and executable_path.parent.name.casefold() == "scripts"
        and (executable_path.parent.parent / "pyvenv.cfg").is_file()
    )


def _kill_and_reap(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.kill()
    return process.communicate()


def _readline_before(
    process: subprocess.Popen[str],
    *,
    deadline: float,
    original_timeout: float,
) -> str:
    assert process.stdout is not None
    remaining = max(0.0, deadline - monotonic())
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="e00-ready") as executor:
        future = executor.submit(process.stdout.readline)
        try:
            return future.result(timeout=remaining)
        except FutureTimeoutError as exc:
            if process.poll() is None:
                process.kill()
            # Closing the process side of the pipe releases readline before the
            # executor is joined; communicate then drains and reaps the process.
            future.result()
            process.communicate()
            raise subprocess.TimeoutExpired(process.args, original_timeout) from exc


def run_signal_demo(worker_path: Path, *, timeout: float = 5.0) -> ProcessObservation:
    deadline = monotonic() + timeout
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [sys.executable, str(worker_path), "--wait-for-signal"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    startup = _readline_before(
        process,
        deadline=deadline,
        original_timeout=timeout,
    )
    if '"event": "ready"' not in startup:
        stdout, stderr = _kill_and_reap(process)
        raise RuntimeError(f"worker did not become ready: {startup}{stdout}{stderr}")

    if sys.platform == "win32":
        # Windows os.kill(..., SIGTERM) terminates instead of dispatching the
        # Python handler. Raise SIGTERM inside the fixture process so the same
        # cleanup handler remains testable without pretending it is POSIX.
        assert process.stdin is not None
        process.stdin.write("raise-sigterm\n")
        process.stdin.flush()
    else:
        process.send_signal(signal.SIGTERM)
    try:
        remaining = max(0.0, deadline - monotonic())
        stdout, stderr = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        _kill_and_reap(process)
        raise
    return ProcessObservation(
        launcher_pid=process.pid,
        caller_pid=os.getpid(),
        exit_code=process.returncode,
        stdout=startup + stdout,
        stderr=stderr,
        windows_venv_redirector_expected=_is_windows_venv_launcher(sys.executable),
    )
