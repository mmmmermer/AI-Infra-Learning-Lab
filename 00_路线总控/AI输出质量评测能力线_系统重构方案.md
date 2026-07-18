# AI 输出质量评测能力线：系统重构方案

## 定位

这条能力线来自 `2026-06-30 金融代码复合标注员` JD 的路线校准。

它不是新建大模块，也不是替代当前 AI Infra 主线，而是把现有路线中的 RAG、Agent、金融场景、科研实验和 P03 项目连接成一条质量评测闭环。

核心问题：

```text
AI 输出不是只要能生成，还要能被评测、复核、解释和改进。
```

## 和总路线的关系

当前总路线仍然不变：

```text
RAG/Agent 应用
-> AI Workload 抽象
-> 任务队列与调度
-> 监控压测与指标
-> Docker/K8s 云原生部署
-> vLLM/Triton 推理服务
-> 金融投研 AI 场景
```

本能力线嵌入其中：

```text
RAG/Agent 输出
-> citation / step_logs / sources
-> Rubric
-> 人工复核
-> EvaluationTask / ReviewRecord
-> quality metrics
-> P03 平台展示和科研记录
```

## 不做什么

- 不新增 M13。
- 不把岗位 JD 写成你的已完成能力。
- 不做完整标注平台。
- 不做商业 Wind/Bloomberg 接口实操。
- 不把金融评测写成投资建议。
- 不做复杂自动评测系统，第一版保留人工复核和小样本 Rubric。

## 能力结构

下表中的 P03 Agent、EvaluationTask 和 ReviewRecord 均为能力线设计落点；除已单独标明的
RAG retrieval reference 外，不代表 v0.3.1 已实现这些实体或字段。

| 能力层 | 要解决的问题 | 对应模块 | 项目落点 |
|---|---|---|---|
| RAG 质量评测 | 回答是否被来源支持 | M03 | P03 `RagTask` / `EvaluationTask` |
| Agent 轨迹评测 | 工具调用和步骤是否合理 | M04 | P03 planned：`AgentTask.step_logs` |
| Rubric 与人工评测 | 如何定义评分维度和规则 | M11 | `Rubric` / `ReviewRecord` |
| 金融事实核验 | 时间、单位、口径、来源是否正确 | M12 | finance_rag / finance_agent |
| 代码质检辅助 | 语法、逻辑、边界、安全风险 | M01/M02/M11 | 代码评测样例，不抢主线 |
| 指标记录 | 质量指标如何和性能指标并存 | M08 | quality metrics + latency metrics |

## 权威资料依据

| 能力层 | 资料 | 使用方式 |
|---|---|---|
| LLM eval | OpenAI Evaluation best practices | 建立 eval 设计原则和生产系统评测意识 |
| LLM eval | OpenAI Cookbook evaluation flywheel / eval-driven design | 学习从人工错误分析到规则迭代 |
| RAG eval | LangSmith Evaluate a RAG application | 对照 RAG 数据集、评估流程和实验记录 |
| RAG eval | Ragas faithfulness / context precision / context recall | 转化为 RAG 质量指标 |
| Agent eval | OpenAI Agent evals guide | 学习 trace、tool calls、guardrails、handoffs 的评测 |
| Agent eval | LangSmith complex agent / trajectory evals | 转化为 Agent step 和 trajectory review |
| Code review | OWASP Code Review Guide / Secure Code Review Cheat Sheet | 作为 AI 代码输出质检的安全审查框架 |
| Code analysis | GitHub CodeQL docs | 作为长期代码安全自动化参照 |
| Code benchmark | HumanEval / SWE-bench | 理解代码生成评测关注功能正确性和真实 issue |
| Finance docs | SEC EDGAR APIs / fair access | 金融公开文档来源和访问边界 |
| Financial statements | SEC Beginner's Guide / CFA FSA | 三大报表和财务分析基础参照 |

## 模块重构方案

### M03 RAG 工程

新增主线：

```text
answer
-> claims
-> retrieved_sources
-> supported / unsupported
-> faithfulness / citation check
-> review_record
```

需要补强：

- `has_citation` 不只是有无引用，还要看引用是否支撑回答。
- 增加 `unsupported_claim_count`。
- 增加 `hallucination_type`。
- 增加小样本人工评测表。

不改变：

- M03 仍然只保留学习地图 + 适配教材。
- 不做完整自动评测平台。

### M04 Agent 工作流

新增主线：

```text
AgentTask
-> step_logs
-> tool_call
-> expected_tool / actual_tool
-> trajectory_review
-> review_status
```

需要补强：

- 工具调用不只记录成功/失败，还要判断是否“该调用这个工具”。
- 增加 `tool_call_error`。
- 增加 `step_review_note`。
- 增加 Agent 任务拆解质量判断。

不改变：

- 仍然不做多 Agent、自主规划大系统。
- 第一版只评估固定工作流。

### M11 科研方法与实验设计

新增主线：

```text
Rubric
-> 标注样例
-> 人工评测
-> 分歧记录
-> 规则迭代
-> 实验报告
```

需要补强：

- Rubric 设计方法。
- 标注一致性和分歧处理。
- 人工评测记录表。
- 规则迭代记录。

不改变：

- 不虚构实验结论。
- 不提前包装论文结果。

### M12 金融投研 AI 场景

新增主线：

```text
金融回答
-> source_url / document_type / period
-> 数字单位 / 时间口径 / 财报项目
-> risk_note
-> review_record
```

需要补强：

- 财务报表口径核验。
- 时间、单位、币种、同比/环比等常见错误。
- 不把模型输出写成投资建议。

不改变：

- M12 不是金融学大课。
- 不做自动荐股和投资结论。

### P03 AI Workload Platform

规划新增轻量评测链（design-only，v0.3.1 尚未实现）：

```text
RagTask / AgentTask
-> output
-> EvaluationTask
-> Rubric
-> ReviewRecord
-> quality metrics
```

建议字段：

| 字段 | 作用 |
|---|---|
| `evaluation_id` | 评测记录 id |
| `source_task_id` | 被评测的 RagTask / AgentTask |
| `rubric_id` | 使用的评分标准 |
| `review_status` | pending / reviewed / needs_revision |
| `rubric_score` | 人工或半自动评分 |
| `unsupported_claim_count` | 无来源支撑的断言数量 |
| `hallucination_type` | factual / citation / finance_logic / none |
| `logic_error_type` | causality / unit / time / boundary / none |
| `tool_call_error` | wrong_tool / wrong_args / missing_tool / none |
| `reviewer_note` | 人工复核说明 |

## 实验链路建议

第一轮不新建大实验目录，先嵌入已有实验：

| 实验 | 增加内容 |
|---|---|
| E03-02 top-k 对回答质量和延迟的影响 | 增加 `unsupported_claim_count`、`has_citation_support` |
| E03-03 metadata 权限过滤实验 | 增加“越权引用/错误引用”评测 |
| E04-01 工具调用最小实验 | 增加 `expected_tool` / `actual_tool` 对比 |
| E04-02 多步骤状态流转实验 | 增加 step-level review |
| E04-03 人工确认与失败处理实验 | 增加 review_status 和 reviewer_note |
| E08 压测实验 | 保持性能指标，不混淆质量结论 |

后续如果需要，再新增：

```text
E11-01 Rubric 评分一致性实验
```

但本轮先不新建入口，防止实验体系膨胀。

## 学习顺序影响

第一阶段不变：

```text
M00 -> M01 -> M05 -> P01
```

P03 阶段建议调整为：

```text
M03 RAG 最小链路
-> M06 状态持久化
-> M04 Agent 可控工作流
-> M11 Rubric 和人工评测
-> M08 性能与质量指标分离
-> M12 金融事实核验
```

## 表达边界

当前可表达：

```text
正在设计 RAG/Agent 输出质量评测能力线，围绕 citation、unsupported claims、Agent step logs、Rubric 和人工复核建立实验与项目字段。
```

完成 P03 真实实验前不能表达：

- 已完成大模型评测平台。
- 已有金融 AI 评测经验。
- 已证明模型输出质量提升。
- 已完成自动化 hallucination 检测。

完成真实实验后才可表达：

```text
在 P03 中设计并实现 RAG/Agent 输出质量评测流程，记录引用支撑、无来源断言、工具调用错误和人工复核结果，并将质量指标与任务延迟指标分开记录。
```

## 路线偏移检查

| 检查项 | 结论 |
|---|---|
| 是否新增大模块 | 否 |
| 是否打乱 M00/M01/M05/P01 起步 | 否 |
| 是否服务 P03 | 是 |
| 是否服务 M03/M04/M11/M12 | 是 |
| 是否过早做复杂评测平台 | 否 |
| 是否把岗位要求直接包装成成果 | 否 |
| 是否和金融投资建议混淆 | 否 |

## 下一步写入计划

1. 更新 M03 学习地图和资料索引，加入 RAG 输出质量评测。
2. 更新 M04 学习地图和资料索引，加入 Agent 轨迹评测。
3. 更新 M11 学习地图和适配教材，加入 Rubric / 标注 / 人工评测。
4. 更新 M12 学习地图和资料索引，加入金融事实核验。
5. 规划 P03 post-v0.3.1 API 与数据契约，再加入 EvaluationTask / ReviewRecord 轻量字段；当前 reference 不含这些实体。
