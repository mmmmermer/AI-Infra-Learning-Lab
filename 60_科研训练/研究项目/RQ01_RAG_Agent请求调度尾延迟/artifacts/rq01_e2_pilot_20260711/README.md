# RQ01 E2 Synthetic Pilot Reference

Status: `E2 synthetic pilot reference with source snapshot / no P03 or scenario conclusion`.

The original run correctly records `git_worktree_dirty=true`. Commit `f4f48e2`
is a pre-publication local identifier that was later rewritten to remove private
author metadata; it is intentionally not resolvable in the public history. It also
does not contain the research runner, so it is not a sufficient reproduction source.
`source_snapshot.tar.gz` preserves the exact P01 Python sources, tests,
project metadata and dependency lock used by this artifact; its per-file hashes are
in `source_snapshot_files.sha256` and its archive hash is recorded in
`environment.json` and `checksums.sha256`.

The runner executed 30 seeds (17-46), three prediction-error levels and three
strategies. Each condition used 50 warm-up, 500 measurement and 50 cooldown
tasks under one worker and a target utilization of 0.90.

```text
condition-seed runs: 90
strategy runs: 270
workload rows: 54,000
per-task result rows: 162,000
failed runs: 0
```

The main observed tradeoff was stable across the three prediction conditions:
predicted SJF reduced P95 queue wait but increased P99 and long-class P99 queue
wait relative to FIFO. Higher prediction error reduced the P95 improvement and
increased the P99 harm. See `paired_analysis.csv` for seed-level paired
bootstrap intervals and `03_实验记录.md` for the bounded interpretation.

Reproduce in a new directory from the bundled snapshot:

```powershell
tar.exe -xzf .\source_snapshot.tar.gz -C .\rq01-source
Set-Location .\rq01-source
git init
git add .
git -c user.name=artifact -c user.email=artifact@example.invalid commit -m snapshot
Set-Location .\50_项目产出\P01_Mini_Scheduler\mini_scheduler
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe examples\run_rq01_pilot.py `
  --output-dir .\reproduced-rq01-e2
```

Compare regenerated CSV/JSON content after excluding environment-specific fields
such as the new commit id, executable path and machine metadata. A clean rerun from
the snapshot is still required before promoting this pilot to a final research run.

`checksums.sha256` covers every file in this directory except the checksum
manifest itself. The pilot does not include Pareto tails,
on/off bursts, worker-count sensitivity, P03 replay or real RAG/Agent traces.
