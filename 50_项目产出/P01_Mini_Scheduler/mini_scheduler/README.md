# Mini Scheduler

Minimal task scheduling simulator for FIFO, Priority, predicted/oracle SJF, and Cost-aware strategies.

Run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python examples/run_demo.py
```

The historical `sjf` strategy name means predicted SJF and sorts on `estimated_duration`. `oracle_sjf` sorts on actual service time and is only an oracle comparison baseline. The simulator executes `actual_duration` when supplied and falls back to the estimate only for simple teaching fixtures.

The exported standard fixtures set estimates equal to actual durations, so predicted and oracle SJF intentionally match there. `prediction_error_summary.csv` is a deterministic counterexample with underestimation and overestimation. All generated artifacts are reference teaching outputs, not research evidence.

Run the no-dependency smoke check:

```bash
python examples/smoke_check.py
```

Run aging protection experiment:

```bash
python examples/run_aging_experiment.py
```

Export experiment tables:

```bash
python examples/export_results.py
```

Generate SVG charts:

```bash
python examples/generate_svg_charts.py
```

Run the preregistered RQ01 E2 synthetic pilot:

```bash
python examples/run_rq01_pilot.py
```

The default run uses 30 seeds and exports raw workload/task rows, seed-level
summaries, paired bootstrap intervals, environment metadata, and SHA-256
checksums. It is synthetic pilot evidence, not P03 or RAG/Agent evidence.
