# M10 推理 workload 与指标导论学习地图（vLLM / Triton 定位）

## 怎么读这个模块

M10 是长期进阶模块，第一遍只读“推理请求为什么会成为平台压力来源”，不要读成 vLLM/Triton 工程实战或底层性能优化课。原目录名只为兼容现有链接。

阅读主线是：一次生成请求产生 prompt_tokens/output_tokens，进入队列，受到 batching、KV cache、并发和限流影响，最后表现为 TTFT、TPOT、tokens/s、P95/P99。

CUDA、kernel、显存源码先不碰；先能把推理请求建模成 P03 的 `InferenceTask`。

## 在总路线中的位置

M10 是长期进阶模块，用来理解 LLM 推理服务为什么会成为 AI Workload Platform 的核心压力来源。

它不负责第一轮底层优化，也不要求现在部署真实大模型集群。第一版目标是理解推理请求如何产生队列、吞吐、尾延迟、token 成本和监控指标。

主线是：

```text
M03 RAG / M04 Agent
-> generation / inference
-> M10 推理 workload
-> M05 队列和调度
-> M08 监控压测
-> P03 Simulated Inference Worker
-> 后续 vLLM / Triton / Ray Serve
```

## 要解决的问题

- LLM serving 为什么和普通 API 服务不同？
- TTFT、TPOT、tokens/s 分别表示什么？
- batching、KV cache、并发如何影响吞吐和尾延迟？
- 推理请求如何进入队列，为什么调度会影响 P95/P99？
- 推理服务要监控哪些指标？
- vLLM、Triton、Ray Serve 分别解决什么问题？

## 学习目标

- [ ] 能解释 TTFT、TPOT、tokens/s。
- [ ] 能说明 batching、continuous batching 和 KV cache 的直觉作用。
- [ ] 能解释并发、队列、限流、吞吐和尾延迟的关系。
- [ ] 能把推理请求建模成 InferenceTask。
- [ ] 能说明 M05 调度为什么会影响推理 P95/P99。
- [ ] 能列出 M08 需要监控的推理服务指标。
- [ ] 能理解 vLLM/Triton/Ray Serve 的系统定位，并说明当前为什么不能把定位学习写成已完成的工具工程能力。

## 核心内容

| 内容 | 学到什么程度 | 对应出口 |
|---|---|---|
| TTFT | 首 token 等待时间 | E10-02 |
| TPOT | 每 token 生成耗时 | E10-02 |
| tokens/s | 推理吞吐 | E10-02 |
| batching | 合批提高吞吐但可能影响等待 | M05/M08 |
| KV cache | 理解上下文和并发资源压力 | E10-01 |
| 并发 | 观察 queue_length、P95/P99 | E10-02 |
| 队列/限流 | 保护推理服务 | P03 |
| vLLM | LLM serving 和 KV cache/batching 方向 | E10-03 |
| NVIDIA Triton Inference Server | 工业级通用推理服务 | 进阶 |
| OpenAI Triton language/compiler | GPU kernel 编程与编译工具；当前不深入 | 远期 |
| Ray Serve | 可扩展模型服务框架 | 进阶 |

## 对应资料

- [[20_资料库/模块资料索引/M10_AI推理系统_vLLM_Triton_资料索引|M10 资料索引]]
- [vLLM Documentation](https://docs.vllm.ai/)
- [vLLM PagedAttention](https://docs.vllm.ai/en/latest/design/paged_attention/)
- [Ray Serve LLM](https://docs.ray.io/en/latest/serve/llm/index.html)
- [NVIDIA Triton Inference Server](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html)

## 对应知识卡片

- [[TTFT]]
- [[TPOT]]
- [[tokens per second]]
- [[KV cache]]
- [[batching]]
- [[continuous batching]]
- [[InferenceTask]]
- [[限流]]

## 对应实验

- [[40_实验练习/E10_推理服务实验/E10_推理服务实验_索引|E10 推理服务实验索引]]
- [[E10-01 模拟推理 worker]]
- [[E10-02 不同请求长度的延迟统计]]
- [[E10-03 vLLM 最小服务实验]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 推荐学习顺序

1. 读 [[M10_AI推理系统_vLLM_Triton_适配教材|M10 适配教材]] 第 1-2 章，理解推理 workload 和 TTFT/TPOT/tokens/s。
2. 读第 3-5 章，理解 batching、KV cache、并发、队列、限流和超时。
3. 读第 6 章，了解 vLLM/Triton/Ray Serve/KServe 的定位。
4. 读第 7 章，把推理服务指标接到 M08。
5. 读第 8 章，规划 E10 模拟推理实验。
6. 后续再做 vLLM 最小服务实验。

## 检查标准

- [ ] 能解释 vLLM 解决什么问题。
- [ ] 能理解 KV cache 和 batching 的意义。
- [ ] 能记录 tokens/s、TTFT、TPOT、P95/P99。
- [ ] 能把推理 worker 接入调度平台。
- [ ] 能说明为什么第一版不深入 CUDA、Triton kernel、显存管理源码、vLLM 内核源码。

## 暂时不深入

- 不学 CUDA。
- 不学 Triton kernel。
- 不读显存管理源码。
- 不读 vLLM 内核源码。
- 不做真实大模型集群调优。
- 不把 vLLM/Triton/Ray Serve/KServe 全部同时部署。
