# M03 RAG 工程学习地图

## 怎么读这个模块

把 M03 当成“一次文档问答请求如何变成可记录、可调度的任务”来读，不要当成 RAG 名词表。

阅读主线是：文档带版本进入系统，失败输入得到确定状态，切成 chunk，在同一黄金集上比较三路检索，
经 tenant/ACL 前置过滤进入不可信 context，返回 sources，并记录质量、生命周期和安全事件。每个概念
都要落到这个流程里的一个可执行断言。

如果看不懂框架名，先忽略框架，抓住 `Document -> Chunk -> Retrieval -> Answer -> Sources -> RagTask` 这条链。

## 在总路线中的位置

M03 位于总路线的应用层入口，负责把“文档问答”变成真实 AI workload。

在当前路线里，RAG 不是孤立 demo，而是下面这条链路的起点：

```text
企业/科研/金融文档
-> RAG 查询请求
-> 可记录的 RagTask
-> M05 队列与调度
-> M08 指标、压测与可观测性
-> P03 AI Workload Platform
```

本模块的重点不是追求复杂框架，而是学会把一次 RAG 请求做成可检索、可引用、可记录、可调度、可评估的最小任务。

正式入口只保留：

1. [[M03_RAG工程_学习地图|M03 RAG 工程学习地图]]
2. [[M03_RAG工程_适配教材|M03 RAG 工程适配教材]]

## 要解决的问题

- 文档如何进入 AI 系统，并保留来源、权限和类型信息？
- 损坏、空白、重复、过期、版本冲突和删除如何得到确定状态？
- 为什么要做 chunk、embedding、top-k 检索和引用溯源？
- 如何用同一黄金集、原始排名和逐 query 分类判断 RAG 真的找到证据？
- 如何让恶意 corpus 可观测，同时隔离 system/context 且不把敏感正文写进日志？
- 如何设计最小评估集，记录失败类型、延迟和 token 成本？
- 如何把 RAG 查询建模成 P03 中可排队、可调度、可监控的任务？

## 学习目标

- [ ] 能画出 `Document -> Chunk -> Embedding -> Retrieval -> Answer -> Sources` 链路。
- [ ] 能解释 metadata 对引用、权限过滤和实验分析的作用。
- [ ] 能说明 chunk_size、overlap、top_k 对质量、延迟和成本的影响。
- [ ] 能解释为什么 RAG 是 AI workload，而不是一次普通问答函数。
- [ ] 能说明 `document_id`、`chunk_id`、`task_id` 分别追踪什么对象。
- [ ] 能设计一个小评估集，记录命中来源、失败类型、latency 和 token_count。
- [ ] 能比较 lexical/vector/hybrid，并从原始排名复算 Recall@k、MRR 和 nDCG。
- [ ] 能设计 ingestion failure matrix，并验收删除后的索引、cache 与旧版本 replay。
- [ ] 能解释 Mock generation 只证明控制流边界，不代表真实模型普遍抗注入。
- [ ] 能把一次 RAG 查询建模成 `RagTask`，并说明它如何进入 M05/M08/P03。

## 核心内容

| 内容 | 学到什么程度 | 落地点 |
|---|---|---|
| Document 与 lifecycle | 会设计 source/version/hash/retention，区分失败状态和 versioned delete | E03 failure matrix 与 P03 `/documents` |
| chunk 策略 | 理解 chunk_size / overlap 的质量和成本取舍 | E03-01 |
| 三路检索 | 在同一黄金集上比较 BM25、固定语义特征 cosine、RRF hybrid，保存可复算排名 | E03-01/E03-02 reference |
| rerank | 知道它是检索结果的二次排序，第一轮只作为质量改进点 | E03-02 的可选观察 |
| answer 与 retrieved_sources | 能返回结构化回答和引用来源 | P03 的 RAG Worker 输出 |
| RAG 评估 | 能计算 Recall@k/MRR/nDCG，逐 query 分类，分离质量与 latency | E03 证据 JSON、M08 后续压测 |
| 输出质量评测 | 能判断 answer 是否被 retrieved_sources 支撑，记录 unsupported_claim_count | P03 EvaluationTask |
| metadata 权限过滤 | 能用 server-owned Principal 做 tenant + permission group 前置过滤 | E03-03 |
| corpus 与 prompt 安全 | 能观察 poison/unauthorized hit，结构隔离并生成脱敏审计 | E03-03 对抗 fixture |
| RagTask 建模 | 能把 RAG 请求变成队列任务 | M05 调度与 P03 平台 |

## 推荐学习顺序

1. 先读本地图，明确 M03 不做大而全 RAG 百科。
2. 读 [[M03_RAG工程_适配教材|M03 RAG 工程适配教材]] 第 1-2 章，理解 RAG 为什么是 workload 起点。
3. 对照 [[20_资料库/模块资料索引/M03_RAG工程_资料索引|M03 RAG 工程资料索引]]，只查第一轮需要的官方资料。
4. 按教材完成 [[40_实验练习/E03_RAG实验/E03_RAG实验_索引|E03 RAG 实验索引]] 中的三类实验。
5. 最后把 `RagTask`、`RAG Worker`、`metrics` 接回 [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]。

## 对应资料

- [[20_资料库/模块资料索引/M03_RAG工程_资料索引|M03 RAG 工程资料索引]]
- [LangChain RAG 官方文档](https://docs.langchain.com/oss/python/langchain/rag)
- [LlamaIndex RAG 官方文档](https://developers.llamaindex.ai/python/framework/understanding/rag/)
- [Google Cloud RAG reference architectures](https://docs.cloud.google.com/architecture/rag-reference-architectures)
- [OpenAI Cookbook](https://developers.openai.com/cookbook)
- [LangSmith Evaluate a RAG application](https://docs.langchain.com/langsmith/evaluate-rag-tutorial)
- [Ragas metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [Ragas Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
- [Elasticsearch similarity / BM25](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html)
- [NIST TREC](https://trec.nist.gov/)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [OWASP Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)

## 对应知识卡片

- [[RAG]]
- [[chunk 策略]]
- [[embedding]]
- [[向量数据库]]
- [[metadata 过滤]]
- [[RAG 评估]]
- [[AI workload]]

## 对应实验

- [[40_实验练习/E03_RAG实验/E03_RAG实验_索引|E03 RAG 实验索引]]
- [[E03-01 chunk 大小对检索效果的影响]]
- [[E03-02 top-k 对回答质量和延迟的影响]]
- [[E03-03 metadata 权限过滤实验]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service]]：作为可选拆分项目，不替代 P03 主线。

## 检查标准

- [ ] 能实现最小文档输入、chunk、检索、回答和 retrieved_sources 返回。
- [ ] 能解释 chunk_size、overlap、top_k 的质量和成本影响。
- [ ] 能设计并记录 E03-01、E03-02、E03-03 的实验观察。
- [ ] 能证明三种检索使用同一黄金集，并复算一条 hybrid RRF 和三个检索指标。
- [ ] 能给 ingestion failure matrix 的每个 case 产生唯一状态。
- [ ] 能证明删除推进 collection version、清理旧缓存、移除 chunk 并拒绝低版本复活。
- [ ] 能观察 poison/unauthorized context，越权时 fail closed，且审计不含原始 query、正文或 user ID。
- [ ] 能记录 `latency_ms`、`token_count`、`retrieved_chunk_count`、`error_type`。
- [ ] 能用小样本 Rubric 判断回答是否被 retrieved_sources 支撑。
- [ ] 能记录 `unsupported_claim_count`、`has_citation_support`、`hallucination_type`。
- [ ] 能解释 overlap 设置错误为什么会导致重复成本甚至切分卡住。
- [ ] 能解释为什么只保存 answer、不保存 retrieved_sources 会破坏复盘。
- [ ] 能说明 RAG Worker 与 Scheduler 的边界。
- [ ] 能把 RAG 请求接入 P03 的任务队列和指标体系。

## 暂时不深入

- 不做复杂 Agent 工具调用和多轮记忆。
- 不做大规模向量数据库选型和集群部署。
- 不做完整企业权限系统，只做 server-owned principal、tenant/ACL 前置过滤和 scoped cache。
- 不做复杂 PDF/Word/OCR 解析器，但要用损坏/空白 fixture 验证 parser 失败状态。
- 不做生产 dense embedding 和复杂 hybrid 调参，只保留可复算三路教学基线。
- 不做真实模型抗注入结论或跨存储删除承诺，只验收 Mock 控制流和内存生命周期。
- 不做自动化 RAG 评测平台，第一轮先手工小评估集。
- 不把 LangChain / LlamaIndex 从头到尾学完，只按任务查官方资料。
