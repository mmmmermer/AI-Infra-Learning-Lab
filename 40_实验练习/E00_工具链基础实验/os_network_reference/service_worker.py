from __future__ import annotations

import argparse
from threading import Event
import json
import os
import signal
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--wait-for-signal", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.wait_for_signal:
        print(
            json.dumps(
                {
                    "event": "exit",
                    "pid": os.getpid(),
                    "parent_pid": os.getppid(),
                    "demo_mode": os.environ.get("DEMO_MODE", "unset"),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return args.exit_code

    shutdown_requested = Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        print(
            json.dumps(
                {"event": "signal", "signal": signal.Signals(signum).name},
                sort_keys=True,
            ),
            flush=True,
        )
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_shutdown)
    print(
        json.dumps(
            {"event": "ready", "pid": os.getpid(), "parent_pid": os.getppid()},
            sort_keys=True,
        ),
        flush=True,
    )
    if sys.platform == "win32":
        command = sys.stdin.readline().strip()
        if command == "raise-sigterm":
            signal.raise_signal(signal.SIGTERM)
    if not shutdown_requested.wait(timeout=10):
        print(json.dumps({"event": "shutdown_timeout"}), flush=True)
        return 124
    print(json.dumps({"event": "cleanup", "status": "complete"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
