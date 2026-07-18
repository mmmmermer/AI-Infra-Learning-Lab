# E03-02 top-k 对回答质量和延迟的影响

> 当前状态：`draft / partial / unverified`。正式实验必须复用 E03-01 的固定 corpus、黄金集和检索器；不得用手工排序、模板延迟或主观回答质量形成结论。retrieval 与 generation 分开评价。

`e03_rag_reference/` 已提供检索 top-k 的可执行 baseline；真实生成和 citation precision/recall 仍未实现，因此本页整体仍不能标记为完整 RAG verified。

## 实验定位

本实验用于观察 `top_k` 如何影响 RAG 的回答质量、引用覆盖、噪声、延迟和 token 成本。

它不是为了追求复杂 rerank 或自动评测平台，而是回答一个工程问题：

```text
一次 RAG 查询到底应该取回几个 chunk？
```

如果 `top_k` 太小，可能缺少关键证据；如果 `top_k` 太大，可能引入噪声、增加 prompt 长度、提高生成延迟。

## 前置阅读

- [[10_学习模块/M03_RAG工程/M03_RAG工程_适配教材|M03 RAG 工程适配教材]]
- [[40_实验练习/E03_RAG实验/E03-01 chunk 大小对检索效果的影响|E03-01 chunk 大小对检索效果的影响]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_适配教材|M08 监控压测与可观测性适配教材]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 实验目标

- [ ] 能比较 `top_k=1/3/5/8` 的检索结果差异。
- [ ] 能判断回答是否被 sources 支撑。
- [ ] 能记录 `retrieved_sources`、`answer_supported`、`has_citation`、`latency_ms`、`token_count`。
- [ ] 能说明 `top_k` 如何影响 P03 的 RAG worker 和 M08 指标。

## 测试数据

沿用 [[E03-01 chunk 大小对检索效果的影响]] 的自造短文档。

本实验建议先固定 chunk 参数：

```text
chunk_size = 160
overlap = 30
```

补充一个用于噪声观察的自造文档：

```yaml
document_id: doc_noise_001
doc_type: general_note
permission_group: public
source: self_made_test_data
title: 无关背景测试片段
```

```text
这是一个无关背景片段，讨论团队会议、页面配色和文档命名规范。
它不包含 RAG、调度、合规条款或金融公告的核心答案。
加入它是为了观察 top_k 变大时是否会把无关内容带入上下文。
```

## 实验问题

至少使用下面 4 个 query：

| query_id | query | expected_sources |
|---|---|---|
| Q1 | RAG 回答为什么需要 sources？ | doc_course_rag_001 |
| Q2 | SJF 可能带来什么调度副作用？ | doc_exp_scheduler_001 |
| Q3 | 合规条款样例要求卖方做什么？ | doc_compliance_clause_001 |
| Q4 | 金融公告样例中提到了哪些风险？ | doc_finance_notice_001 |

## 实验步骤

### 步骤 1：固定 chunk 设置

使用 E03-01 中表现相对稳定的一组参数，例如：

```text
chunk_size = 160
overlap = 30
```

### 步骤 2：设置 top_k 组别

| 组别 | top_k | 观察重点 |
|---|---:|---|
| A | 1 | 是否容易漏证据 |
| B | 3 | 第一轮基线 |
| C | 5 | 是否增加覆盖 |
| D | 8 | 是否引入明显噪声和成本 |

### 步骤 3：执行检索

每个 query 分别用 `top_k=1/3/5/8` 检索。

第一轮使用 E03-01 锁定的 BM25 baseline。若切换 embedding，需要作为新的独立实验配置，不能与 BM25 结果混在同一组 top-k 对比中。

### 步骤 4：分别评价 retrieval 与 generation

retrieval 先用 `recall@k`、MRR/nDCG 评价。只有接入真实生成调用后才记录 `generation_ms`；模板回答可以检查字段结构，但不得填写生成延迟或形成生成质量结论。

```json
{
  "answer": "...",
  "retrieved_sources": ["doc_course_rag_001_chunk_2"],
  "has_citation": true,
  "risk_note": "该回答仅基于测试文档生成。"
}
```

### 步骤 5：判断质量和延迟

对每条记录判断：

- 是否命中 expected source？
- 是否有无关 chunk？
- answer 是否被 sources 支撑？
- top_k 增加后 latency_ms 和 token_count 是否上升？

## 观察指标

| 指标 | 说明 | 对 P03 的意义 |
|---|---|---|
| top_k | 检索片段数 | RagTask 输入参数 |
| expected_sources_hit | 是否命中预期来源 | 质量判断 |
| retrieved_sources | 实际来源 | result_json.retrieved_sources |
| noise_count | 无关片段数量 | 检索噪声 |
| answer_supported | 回答是否被来源支撑 | RAG 质量 |
| has_citation | 是否带引用 | P03 展示和评估 |
| citation_count | 引用数量 | M12/M08 场景指标 |
| estimated_token_count | 上下文估计长度 | 成本和生成耗时 |
| retrieval_ms | 检索耗时 | M08 指标 |
| generation_ms | 真实生成调用耗时；未调用时必须为空 | M08 指标 |
| citation_precision / citation_recall | 引用是否准确覆盖黄金证据 | 生成质量与证据绑定 |
| error_type | 失败类型 | 错误分析 |

## 记录表

| query_id | top_k | expected_sources | retrieved_sources | expected_sources_hit | noise_count | answer_supported | has_citation | citation_count | estimated_token_count | retrieval_ms | generation_ms | error_type | 观察 |
|---|---:|---|---|---|---:|---|---|---:|---:|---:|---:|---|---|
| Q1 | 1 | doc_course_rag_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q1 | 3 | doc_course_rag_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q1 | 5 | doc_course_rag_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q1 | 8 | doc_course_rag_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q2 | 1 | doc_exp_scheduler_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q2 | 3 | doc_exp_scheduler_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q3 | 3 | doc_compliance_clause_001 |  |  |  |  |  |  |  |  |  |  |  |
| Q4 | 3 | doc_finance_notice_001 |  |  |  |  |  |  |  |  |  |  |  |

## 常见错误

| 错误 | 表现 | 修正 |
|---|---|---|
| top_k 越大越好 | 噪声和 token 成本上升 | 同时记录 noise_count 和 token_count |
| 只记录 answer | 无法判断检索问题还是生成问题 | 必须记录 retrieved_sources |
| 不固定 chunk 参数 | 混淆 top_k 和 chunk 影响 | 本实验固定 chunk_size / overlap |
| 忽略延迟 | 质量看似提升但系统变慢 | 记录 retrieval_ms 和 generation_ms |
| 没有 error_type | 失败不可复盘 | 记录 no_relevant_chunk、too_much_noise、citation_missing |

## 验收标准

- [ ] 至少完成 4 个 query 和 4 组 top_k 的对比。
- [ ] 能指出一个较适合 P03 RAG v1 的 top_k 初始值。
- [ ] 能解释 top_k 增大对 citation、noise、token_count、latency 的影响。
- [ ] 能记录至少 3 类失败或风险：`no_relevant_chunk`、`too_much_noise`、`citation_missing`。
- [ ] 未执行真实生成时，`generation_ms` 和生成质量结论保持为空。
- [ ] 能说明该实验如何接入 M08 的压测和 P03 的 metrics。

## 关联 P03 字段

| 实验字段 | P03 字段 |
|---|---|
| query | query |
| top_k | top_k |
| retrieved_sources | result_json.retrieved_sources |
| citation_count | result_json.metrics.citation_count |
| has_citation | has_citation |
| estimated_token_count | token_count |
| retrieval_ms | retrieval_ms |
| generation_ms | generation_ms |
| error_type | error_type |
| answer_supported | result_json.quality.answer_supported |

## 后续连接

- 接 [[E03-03 metadata 权限过滤实验]]，观察权限过滤是否在 top_k 前后生效。
- 接 [[40_实验练习/E08_监控压测实验/E08_监控压测实验_索引|E08 监控压测实验索引]]，把 top_k 作为压测变量。
- 接 [[10_学习模块/M12_金融投研AI场景/M12_金融投研AI场景_适配教材|M12 金融投研 AI 场景适配教材]]，观察金融/合规文档的引用和风险提示。
