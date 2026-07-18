# M10 AI 推理系统 vLLM Triton 资料索引

## 当前策略

推理系统资料属于长期进阶。第一轮只服务于理解推理 workload 对 P03 的队列、吞吐、尾延迟和监控指标的影响。

资料不是底层优化清单。当前不进入 CUDA、Triton kernel、显存管理源码、vLLM 内核源码。

## 资料闭环

```text
M10 学习地图
-> M10 导论型适配教材
-> 本资料索引按需查官方资料
-> E10 推理服务实验
-> P03 Simulated Inference Worker
```

## 资料列表

| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M10 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| vLLM Documentation | https://docs.vllm.ai/ | 官方文档 | 必读 | 入门 | 了解 vLLM 是 LLM serving 系统 | 第 6 章 |
| vLLM PagedAttention Docs | https://docs.vllm.ai/en/latest/design/paged_attention/ | 官方文档 | 选读 | KV cache | 只理解 KV cache 管理和吞吐方向 | 第 4 章 |
| vLLM Metrics | https://docs.vllm.ai/en/latest/usage/metrics.html | 官方文档 | 必读 | 监控 | 查 TTFT、tokens、队列、吞吐等指标出口 | 第 7 章 |
| vLLM PagedAttention Paper | https://arxiv.org/abs/2309.06180 | 论文 | 暂缓 | 科研 | 后续理解论文，不作为第一轮教材重点 | 进阶 |
| NVIDIA Triton Docs | https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html | 官方文档 | 选读 | 推理服务 | 理解通用推理服务系统定位 | 第 6 章 |
| Ray Serve LLM | https://docs.ray.io/en/latest/serve/llm/index.html | 官方文档 | 选读 | LLM 服务部署 | 理解 Ray Serve 作为模型服务框架 | 第 6 章 |
| KServe Docs | https://kserve.github.io/website/ | 官方文档 | 暂缓 | K8s 模型服务 | 连接 M09 云原生模型服务方向 | 进阶 |

## 教材章节对应

| 教材章节 | 主要资料 | 使用方式 |
|---|---|---|
| 第 1 章：推理服务压力来源 | P03/M05/M08 | 从 workload、队列和指标理解 |
| 第 2 章：TTFT/TPOT/tokens/s | vLLM Metrics | 查推理指标 |
| 第 3 章：batching 和并发 | vLLM docs | 理解 serving 吞吐方向 |
| 第 4 章：KV cache | vLLM PagedAttention Docs | 只理解资源压力，不读源码 |
| 第 5 章：队列、限流、超时 | M05/M08 | 接调度和监控 |
| 第 6 章：vLLM/Triton/Ray Serve | 官方文档 | 只讲系统定位 |
| 第 7 章：监控指标 | vLLM Metrics、M08 | 形成 P03 指标表 |
| 第 8 章：实验规划 | E10 | 先模拟，再最小 vLLM |

## 对应实验

- [[40_实验练习/E10_推理服务实验/E10_推理服务实验_索引|E10 推理服务实验索引]]
- [[E10-01 模拟推理 worker]]
- [[E10-02 不同请求长度的延迟统计]]
- [[E10-03 vLLM 最小服务实验]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 和相关模块的关系

- M03：RAG generation 会调用推理服务。
- M04：Agent 报告生成会产生更长、更不稳定的推理请求。
- M05：推理请求进入队列，调度影响 P95/P99。
- M08：推理服务需要 TTFT、TPOT、tokens/s、queue_wait、error_rate 等指标。
- M09：后续模型服务可能部署到 Kubernetes。

## 不做

- 不先学 CUDA / 算子优化。
- 不先部署真实大模型集群。
- 不读 vLLM 内核源码。
- 不深入 Triton kernel。
- 不脱离调度和服务化主线。

## 转化检查

- [ ] 每条必读资料能转化成教材章节、E10 实验或 P03 指标。
- [ ] M10 没有偏成底层推理优化。
- [ ] M10 能连接 M05 调度和 M08 监控。
