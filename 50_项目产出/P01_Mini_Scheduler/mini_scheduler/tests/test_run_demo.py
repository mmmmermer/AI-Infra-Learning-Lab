from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_demo_command_is_executable() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(project_root / "examples" / "run_demo.py")],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    output = result.stdout
    for strategy_name in ("fifo", "priority", "sjf", "cost_aware"):
        assert f"{strategy_name} |" in output
