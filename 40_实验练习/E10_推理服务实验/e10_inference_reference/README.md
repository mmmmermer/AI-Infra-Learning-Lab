# E10 deterministic inference reference

This package models inference requests without sleeping, calling a model, or claiming real GPU performance. It exists to verify metric definitions and queue accounting before a real serving experiment.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python -m e10_reference.demo
```

The model separates:

- service time from queue wait
- TTFT from total latency
- TPOT from output throughput
- per-request metrics from aggregate output tokens per second

Aggregate throughput is reported only for the complete shared-worker workload. Per-kind summaries omit throughput because request kinds share one worker and their isolated time spans would be misleading.

The constants are synthetic parameters, not measurements from vLLM, NVIDIA Triton Inference Server, a GPU, or any production service.
