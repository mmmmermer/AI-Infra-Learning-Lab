# M00 OS and request-path reference

This Python 3.13 reference uses only the standard library at runtime and does not access the network.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

The 11-test suite verifies observable process metadata and exit codes, bounded startup and execution timeouts that
kill and reap the child, graceful `SIGTERM` cleanup, permission preflight and recovery, and deterministic
DNS/TCP/TLS/HTTP failure classification. The signal fixture uses one total deadline for both readiness and shutdown;
silent and late-ready workers are killed before they can produce a delayed side effect. POSIX sends `SIGTERM` from the parent.
On POSIX and with a direct interpreter launch, the worker PID equals `Popen.pid` and its PPID is the test process.
A Windows virtual environment may instead run `Scripts\python.exe` as a redirector: `Popen.pid` is then the
launcher, and the worker reports that launcher as its PPID. The test accepts only those two exact topologies and
only permits the redirector form when the executable is verified as a Windows venv launcher.

Windows raises `SIGTERM` inside the child fixture because Windows `os.kill(..., SIGTERM)` performs unconditional
termination rather than dispatching Python's handler. This proves handler cleanup, not POSIX signal delivery.
The injected request stages are diagnostic fixtures, not a packet capture or a production probe.
