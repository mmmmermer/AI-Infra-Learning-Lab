# E03-01 chunk 大小对检索效果的影响

> 当前状态：`draft / partial / unverified`。本页原先允许关键词匹配和手工排序，不能据此比较 chunk 参数。修订后的正式实验必须使用固定 corpus、独立黄金 query/evidence 集、锁定版本的确定性 BM25 或 embedding，并用真实计时和检索指标验收。

已补可执行参考：`e03_rag_reference/`，Python 3.13 下测试通过。该 reference 验证检索实验方法，不代表真实生产 RAG 结论。

## 实验定位

本实验用于观察 `chunk_size` 和 `overlap` 如何影响 RAG 检索效果、引用质量、片段数量和估计成本。

它不是为了找到“永远最优”的 chunk 参数，而是训练你用小实验判断：

```text
文档切得太碎会不会丢上下文？
文档切得太大会不会带来噪声？
overlap 是否真的改善命中？
chunk 数量增加后，P03 的 token_count 和 latency_ms 会不会上升？
```

实验结果服务 P03 的 `RagTask` 字段设计和后续 M08 压测指标。

## 前置阅读

- [[10_学习模块/M03_RAG工程/M03_RAG工程_学习地图|M03 RAG 工程学习地图]]
- [[10_学习模块/M03_RAG工程/M03_RAG工程_适配教材|M03 RAG 工程适配教材]]
- [[20_资料库/模块资料索引/M03_RAG工程_资料索引|M03 RAG 工程资料索引]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 实验目标

- [ ] 能用同一批文档生成不同 chunk 设置下的片段。
- [ ] 能比较不同 chunk 参数下的命中来源。
- [ ] 能在独立黄金集中计算 `recall@k`、MRR 或 nDCG。
- [ ] 能记录 `chunk_count`、`retrieved_sources`、`has_citation`、`latency_ms`、`token_count`。
- [ ] 能判断 chunk 参数如何影响 P03 的 RAG workload。

## 测试数据

第一轮使用自造短文档，不代表真实金融、法律、合规或投资结论。

### 文档 A：课程笔记

```yaml
document_id: doc_course_rag_001
doc_type: course_note
permission_group: public
source: self_made_test_data
title: RAG 基础笔记
```

```text
RAG 是 Retrieval-Augmented Generation 的缩写。它的基本流程是先把文档切分成 chunk，
再为 chunk 建立 embedding，用户提问时检索相关 chunk，最后把检索结果作为上下文交给模型生成回答。
chunk_size 太小可能导致语义被切断，chunk_size 太大可能引入无关信息并增加 token 成本。
overlap 可以缓解边界处的信息丢失，但也会增加重复内容和索引规模。
```

### 文档 B：实验记录

```yaml
document_id: doc_exp_scheduler_001
doc_type: experiment_note
permission_group: public
source: self_made_test_data
title: 调度实验记录
```

```text
在高峰负载下，FIFO 调度的平均等待时间较高，但不同任务之间比较公平。
SJF 可以降低短任务的平均等待时间，但可能让长任务等待更久，从而影响 P95 或 P99。
worker 数量增加通常会降低等待时间，但如果 worker 过多，worker utilization 可能下降。
```

### 文档 C：合规条款样例

```yaml
document_id: doc_compliance_clause_001
doc_type: compliance_clause
permission_group: public
source: self_made_test_data
title: 合规条款测试片段
```

```text
本合同样例要求卖方提供出口合规声明，并在发货前确认货物不属于受限制清单。
如果买方要求变更目的地，卖方应重新检查贸易合规风险。
该样例仅用于 RAG 实验，不构成法律意见。
```

### 文档 D：金融公告样例

```yaml
document_id: doc_finance_notice_001
doc_type: finance_notice
permission_group: public
source: self_made_test_data
title: 金融公告测试片段
```

```text
某公司公告称，本季度收入增长主要来自云服务业务，但管理层同时提示宏观环境和供应链波动可能影响后续交付。
该文本为自造测试数据，仅用于观察 RAG 检索、引用和风险提示，不构成投资建议。
```

## 实验步骤

### 步骤 1：固定查询问题

至少使用下面 3 个 query：

```text
Q1: chunk_size 太小或太大会带来什么问题？
Q2: SJF 为什么可能影响 P95 或 P99？
Q3: 合规条款样例中要求卖方做什么？
```

### 步骤 2：设置三组 chunk 参数

| 组别 | chunk_size | overlap | 目的 |
|---|---:|---:|---|
| A | 80 | 0 | 观察切得很碎时是否丢上下文 |
| B | 160 | 30 | 第一轮推荐基线 |
| C | 320 | 50 | 观察大 chunk 是否引入噪声 |

切分器必须固定并记录版本。第一轮可以使用字符长度切分，但所有组必须使用同一实现，且记录边界规则；不能一边改变 chunk 参数，一边改变 tokenizer 或清洗逻辑。

### 步骤 3：生成 chunks

记录每组参数生成的 chunk 数量。

```text
document_id
chunk_id
chunk_text
chunk_size
overlap
metadata
```

### 步骤 4：执行检索

使用锁定版本的确定性 BM25 作为第一条 baseline。手工排序只能用于检查黄金集，不能作为实验结果。若改用 embedding，必须固定模型名、版本、维度、归一化方式、距离度量和索引版本。

每个 query 在每组 chunk 参数下记录 top-3 候选片段，并将检索结果与独立黄金 evidence id 对比。

### 步骤 5：判断引用是否支撑回答

对每个 query 判断：

- 是否找到了 expected source？
- retrieved chunk 是否包含足够上下文？
- answer 是否能被 sources 支撑？
- 是否出现无关片段？

## 观察指标

| 指标 | 说明 | 对 P03 的意义 |
|---|---|---|
| chunk_count | 生成片段数量 | 影响索引规模和检索成本 |
| retrieved_sources | 命中的来源 chunk | 影响 answer 是否可引用 |
| answer_supported | 回答是否被来源支撑 | 影响质量判断 |
| has_citation | 是否能返回引用 | P03 RAG 输出字段 |
| estimated_token_count | 估计上下文 token 数 | 影响成本和生成耗时 |
| retrieval_ms | 用 `perf_counter` 实际测得的检索耗时 | 后续接 M08 |
| recall@k / MRR / nDCG | 检索排序质量 | 不能用主观回答流畅度替代 |
| noise_count | 无关片段数量 | 判断 chunk 是否过大或检索过宽 |
| error_type | 失败类型 | P03 错误分析 |

## 记录表

| query_id | chunk_size | overlap | chunk_count | top_k | expected_sources | retrieved_sources | answer_supported | has_citation | estimated_token_count | latency_ms | noise_count | error_type | 观察 |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|---|---|
| Q1 | 80 | 0 |  | 3 | doc_course_rag_001 |  |  |  |  |  |  |  |  |
| Q1 | 160 | 30 |  | 3 | doc_course_rag_001 |  |  |  |  |  |  |  |  |
| Q1 | 320 | 50 |  | 3 | doc_course_rag_001 |  |  |  |  |  |  |  |  |
| Q2 | 80 | 0 |  | 3 | doc_exp_scheduler_001 |  |  |  |  |  |  |  |  |
| Q2 | 160 | 30 |  | 3 | doc_exp_scheduler_001 |  |  |  |  |  |  |  |  |
| Q3 | 160 | 30 |  | 3 | doc_compliance_clause_001 |  |  |  |  |  |  |  |  |

## 常见错误

| 错误 | 表现 | 修正 |
|---|---|---|
| 只看回答是否流畅 | answer 看起来对，但没有来源支撑 | 必须记录 retrieved_sources 和 has_citation |
| 每组参数换不同文档 | 无法比较 chunk 参数影响 | 固定同一批文档和 query |
| 只记录命中，不记录噪声 | 看不到大 chunk 的副作用 | 记录 noise_count |
| 用真实金融结论做样例 | 容易虚构或误导 | 第一轮使用自造测试数据或公开可核验来源 |
| 把实验写成教程 | 失去可复盘性 | 用记录表保存每次实验设置和结果 |

## 验收标准

- [ ] 至少完成 3 个 query、3 组 chunk 参数的对比。
- [ ] 每条记录都有 `retrieved_sources`、`retrieval_ms`、`estimated_token_count` 和检索质量指标。
- [ ] corpus、黄金集、切分器和检索器版本固定且可重放。
- [ ] 能说明哪组 chunk 参数更适合作为 P03 RAG v1 的基线。
- [ ] 能指出至少一种失败类型，例如 `chunk_too_small`、`chunk_too_large`、`no_relevant_chunk`。
- [ ] 能把实验字段映射到 P03 的 RagTask 或 metrics。

## 关联 P03 字段

| 实验字段 | P03 字段 |
|---|---|
| query | query |
| chunk_size / overlap | input_json 或 collection_config |
| top_k | top_k |
| retrieved_sources | result_json.retrieved_sources |
| chunk_count | retrieved_chunk_count / collection_stats |
| has_citation | has_citation |
| estimated_token_count | token_count |
| latency_ms | retrieval_ms |
| error_type | error_type |

## 后续连接

- 接 [[E03-02 top-k 对回答质量和延迟的影响]]，继续观察 top_k。
- 接 [[E08_监控压测实验_索引]]，把 `latency_ms` 迁移成压测指标。
- 接 [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]] 的 RAG v1。
