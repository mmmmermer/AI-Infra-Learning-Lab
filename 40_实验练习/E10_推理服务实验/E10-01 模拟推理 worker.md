# E10-01 模拟推理 worker

> 状态（2026-07-18）：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`。`e10_inference_reference/` 在 Python 3.13 下 7 个测试通过；它不调用模型、不休眠，也不代表任何 GPU 或 vLLM 性能。

## 实验目的

先用确定性模型把推理任务、服务时间、队列等待、TTFT 和 TPOT 分开。第一轮要验证的是指标语义和调度输入，不是拟真硬件性能。

## 参考任务模型

```python
InferenceTask(
    task_id="task-01",
    request_kind="rag_answer",
    arrival_ms=0,
    prompt_tokens=2000,
    output_tokens=300,
)
```

字段约束：

- `arrival_ms >= 0`
- `prompt_tokens >= 0`
- `output_tokens >= 1`
- `request_kind` 用于分组，不能代替真实模型、硬件和版本信息

## 简化成本模型

参考实现使用：

```text
prefill_ms = prompt_tokens * prefill_ms_per_token
decode_ms = output_tokens * decode_ms_per_token
service_ms = fixed_overhead_ms + prefill_ms + decode_ms
queue_wait_ms = start_ms - arrival_ms
total_latency_ms = queue_wait_ms + service_ms
ttft_ms = queue_wait_ms + fixed_overhead_ms + prefill_ms + one_decode_step
tpot_ms = decode_ms_per_token, only when output_tokens > 1
```

这些常数是合成参数，只用于单元测试和调度直觉。不能把它们写成“RTX 4060、vLLM 或某模型的实测速度”。

## 运行

```powershell
cd 40_实验练习\E10_推理服务实验\e10_inference_reference
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python -m e10_reference.demo
```

## 必须理解的指标边界

| 指标 | 本参考实现中的定义 | 不能混同为 |
|---|---|---|
| `queue_wait_ms` | 到达后等待单 worker 可用的时间 | 模型计算时间 |
| `service_ms` | 合成 prefill + decode + 固定开销 | 端到端延迟 |
| `ttft_ms` | queue + fixed + prefill + 首次 decode | 纯 prefill |
| `tpot_ms` | 首 token 之后的平均 decode step；单输出 token 时缺失 | 总延迟 / token 数 |
| `aggregate_output_tokens_per_second` | 总输出 token / 整段 workload makespan | 单请求瞬时速度 |

aggregate throughput 只对完整的共享 worker workload 计算；按请求类型分组时不重复计算吞吐，避免把其他类型占用 worker 的时间错误归到某一组。

真实服务的 TTFT/TPOT 定义应与具体 benchmark 工具和服务版本核对，并在报告中固定公式。

## P03 接口边界

当前 P03 已允许 `task_type="simulated_inference"`，但 worker 只回显输入，并没有使用本页成本模型。接入 P03 时应显式保存：

```text
prompt_tokens
output_tokens
profile_version
estimated_service_ms
actual_service_ms
queue_wait_ms
ttft_ms
tpot_ms
```

在没有真实 streaming token 时间戳时，字段必须标为 `estimated_*` 或 `simulated_*`，不能写成 actual TTFT/TPOT。

## 学习者验收

- [ ] 能解释 service time 和 queue wait 的区别。
- [ ] 能手算一个任务的 TTFT、TPOT 和 total latency。
- [ ] 能运行测试和 demo，并保存自己的输出。
- [ ] 能说明为什么合成模型不能支撑硬件或 serving 系统结论。
- [ ] 能为 profile 参数增加版本和来源记录。

## 边界

本实验不加载模型、不测显存、不测 CUDA、不验证 batching/KV cache，也不生成真实回答。
