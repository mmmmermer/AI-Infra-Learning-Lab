# M01 concurrency and cancellation reference

This Python 3.13 standard-library reference separates three decisions:

- blocking I/O that must keep a synchronous API uses a thread pool;
- CPU-bound Python work uses a process pool;
- many cooperative waits use `asyncio`, provided blocking calls are offloaded.

Create the pinned Python 3.13 development environment and run the deterministic contract tests from this directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

The blocking-I/O example records a small timing comparison as teaching evidence, not as a production benchmark.
The event-loop contract does not compare elapsed time: start/release gates prove whether a callback can run while
synchronous work still owns the worker boundary. Cancellation is not considered complete until the cancelled task
has been awaited and its resource probe reports a matching release. The offload helper also shields and joins its
worker during cancellation so its coroutine cannot finish while the underlying thread is still running.
