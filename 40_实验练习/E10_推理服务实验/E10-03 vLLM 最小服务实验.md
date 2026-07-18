# E10-03 vLLM 最小服务实验

> 状态（2026-07-18）：`内容 content-reviewed / 实现 absent (environment-blocked) / Reference unverified / 教学 partial / 归属 reference / 学习者 not-evaluated`。当前主机只有 Windows 主环境和 Docker Desktop 的内部 WSL 发行版，没有独立 Linux/WSL 学习环境；vLLM 不原生支持 Windows，因此本实验不能标记为已验证。

## 实验目的

在独立 Linux 或 WSL2 环境中启动一个小模型的 vLLM OpenAI-compatible server，发送少量固定请求，并记录环境、TTFT、TPOT、总延迟、tokens/s 和错误。目标是理解 serving 接口与指标，不做多 GPU 或生产调优。

## 名称边界

本路线中的两个 Triton 不是同一项目：

| 名称 | 定位 |
|---|---|
| NVIDIA Triton Inference Server | 通用模型推理服务系统，提供模型仓库、后端、动态 batching 和服务接口 |
| OpenAI Triton language/compiler | 编写高性能 GPU kernel 的语言和编译器生态 |

vLLM 可能在底层使用 Triton kernel，但这不等于本实验部署了 NVIDIA Triton Inference Server。E10-03 只验证 vLLM 最小服务。

## 环境门槛

执行前必须记录：

```powershell
wsl --list --verbose
nvidia-smi
```

进入 Linux/WSL 后记录：

```bash
uname -a
cat /etc/os-release
python --version
nvidia-smi
```

最低判断：

- 使用受 vLLM 当前版本支持的 Linux、Python、PyTorch 和 CUDA 组合。
- NVIDIA 驱动能在 Linux/WSL 中看到 GPU。
- 模型权重、KV cache 和运行开销适配可用显存。
- 8 GB 显存只能选择足够小的模型和保守的 `max-model-len`；不能默认任意 7B 模型都能稳定运行。
- 模型许可证、访问权限和磁盘空间已确认。

具体兼容矩阵和安装命令必须以执行当天的 [vLLM 官方安装文档](https://docs.vllm.ai/en/latest/getting_started/installation/) 为准。

## 供应链与访问边界

- 固定 vLLM、PyTorch、CUDA 和模型 revision。
- 记录模型 ID、revision、下载来源和许可证。
- 默认不启用远程自定义代码；若模型必须 `trust_remote_code`，先审查来源并单独记录风险。
- 首次实验只绑定 loopback，不把未鉴权模型服务暴露到局域网或公网。
- 不在 Markdown、日志或命令历史中保存访问 token。

## 计划命令形态

以下是参数结构，不是当前环境已验证的安装配方：

```bash
python -m venv .venv
source .venv/bin/activate
# 按官方兼容矩阵安装锁定版本的 vLLM/PyTorch

vllm serve <pinned-model-id> \
  --revision <model-commit> \
  --host 127.0.0.1 \
  --port 8000 \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.75
```

启动后先检查模型列表和健康状态，再发送固定 prompt。API 路径和 metrics 名称应按所安装 vLLM 版本的官方文档确认，不能从旧教程照抄。

## 测量要求

客户端必须记录 token 到达时间，至少得到：

```text
request_started_at
first_token_at
last_token_at
prompt_tokens
output_tokens
ttft_ms
tpot_ms
total_latency_ms
error_type
```

推荐公式：

```text
TTFT = first_token_at - request_started_at
TPOT = (last_token_at - first_token_at) / (output_tokens - 1), output_tokens > 1
```

还要区分客户端端到端指标与服务端 metrics，二者可能包含不同的网络、排队和序列化开销。

## 最小实验矩阵

| case | prompt_tokens target | max_output_tokens | concurrency | repeats |
|---|---:|---:|---:|---:|
| warmup | short | 32 | 1 | 3 |
| short | 约 256 | 64 | 1 | 至少 20 |
| medium | 约 1024 | 128 | 1 | 至少 20 |
| queue | 固定一种长度 | 64 | 2-4 | 至少 20 |

warmup 结果和正式测量分开。OOM、timeout 和 rate limit 都要作为结果记录，不能静默删掉失败请求。

## 停止与清理

- 停止 vLLM 进程。
- 确认端口不再监听。
- 记录是否保留模型缓存；删除缓存前确认路径，避免误删其他模型。
- 若使用容器，删除实验容器和网络，但不要无差别删除全部镜像/volume。

## 学习者验收

- [ ] 独立 Linux/WSL 环境和 GPU 可见性已验证。
- [ ] 版本、模型 revision 和许可证可追溯。
- [ ] 服务只绑定到受控地址。
- [ ] 客户端能记录首 token 和末 token 时间。
- [ ] warmup、成功、OOM/timeout 等失败路径均有原始记录。
- [ ] 能区分 vLLM、NVIDIA Triton Inference Server 和 OpenAI Triton language。

## 边界

当前页面是环境门槛和实验设计，不是运行报告。没有实际 Linux/WSL、驱动、模型和请求记录前，状态必须保持 `blocked/unverified`。
