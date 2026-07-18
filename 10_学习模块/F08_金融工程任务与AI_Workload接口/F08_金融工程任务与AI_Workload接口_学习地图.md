# F08 金融工程任务与 AI Workload 接口学习地图

## 怎么读这个模块

F08 是金融工程第二主线和 AI Infra 主线的接口模块。

它不再新增很多金融知识，而是回答一个工程问题：

```text
金融工程任务如何变成 P03 可以提交、排队、执行、记录、监控和复核的 workload？
```

第一轮只做任务抽象和字段设计，不做完整平台。

## 在总路线中的位置

```text
F02 金融数据处理
-> F03 风险指标
-> F04 定价任务
-> F06 回测任务
-> F07 模型风险
-> F08 任务接口
-> P03 AI Workload Platform
```

它和 M 系列的连接：

```text
M05 调度
M06 数据库/异步任务
M08 监控指标
M11 实验记录
M12 金融 AI 场景
```

## 要解决的问题

- 金融计算任务和普通脚本有什么区别？
- 一个金融 task 至少需要哪些输入、输出、状态和指标？
- 风险指标、回测、定价、金融 RAG 能否共用任务接口？
- 哪些字段用于工程执行，哪些字段用于合规/风险提示？
- 如何把数据版本、参数、质量评测和人工复核记录到 task 里？
- 什么时候可以写进简历，什么时候只能写成计划或参考？

## 学习目标

- [ ] 能定义 `risk_metric_task` 的 input/output/metrics。
- [ ] 能定义 `backtest_task` 的 input/output/metrics。
- [ ] 能定义 `pricing_task` 的 input/output/metrics。
- [ ] 能定义 `model_risk_task` 和 `data_quality_task` 的 input/output/metrics。
- [ ] 能说明任务状态：pending/queued/running/succeeded/failed。
- [ ] 能说明 quality metrics 和 performance metrics 的区别。
- [ ] 能说明 data lineage、review_status、risk_note、disclaimer 为什么重要。
- [ ] 能连接 M05/M06/M08/P03。
- [ ] 能明确不做投资建议和生产交易系统。

## 核心内容

| task_type | 来源模块 | 输入 | 输出 | 指标 |
|---|---|---|---|---|
| `risk_metric_task` | F02/F03 | price_series、returns、date_range | volatility、VaR、max_drawdown | runtime_ms、missing_ratio |
| `portfolio_task` | F03 | assets、weights、constraints | return、volatility、sharpe | constraint_violations、runtime_ms |
| `pricing_task` | F04/F05 | S、K、r、sigma、T、method | price、greeks | simulation_count、runtime_ms |
| `backtest_task` | F06 | price_series、signal_rule、cost_model | equity_curve、drawdown、turnover | queue_wait_ms、runtime_ms |
| `model_risk_task` | F07/M11 | dataset、features、labels、split_rule | metrics、failure_cases | leakage_flags、review_status |
| `data_quality_task` | F02/M06 | data_source、fields、date_range | missing_ratio、duplicate_rows、field_report | data_version、quality_score |
| `finance_rag_query` | M03/M12 | document_id、query | answer、citations、risk_note | latency_ms、has_citation |

## 统一字段建议

后续所有金融 task 都尽量包含这些字段，方便和 P03、M06、M08、M11 对齐：

```text
task_id
task_type
status
created_at
input_json
result_json
data_source
source_url
data_version
point_in_time_note
parameters
runtime_ms
queue_wait_ms
error_type
quality_flags
review_status
risk_note
disclaimer
```

字段分工：

| 字段组 | 作用 |
|---|---|
| `input_json / parameters` | 复现实验和任务 |
| `data_source / data_version / point_in_time_note` | 说明数据来源和时点口径 |
| `runtime_ms / queue_wait_ms / error_type` | 工程监控 |
| `quality_flags / review_status` | 质量评测和人工复核 |
| `risk_note / disclaimer` | 防止金融结论被误读成投资建议 |

## 对应资料

- [[20_资料库/模块资料索引/F08_金融工程任务与AI_Workload接口_资料索引|F08 金融工程任务与 AI Workload 接口资料索引]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图|M05 任务队列与调度]]
- [[10_学习模块/M06_数据库缓存与异步任务/M06_数据库缓存与异步任务_学习地图|M06 数据库缓存与异步任务]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_学习地图|M08 监控压测与可观测性]]

## 对应实验

- [[40_实验练习/GF10_金融工程全阶段实验候选/GF10_金融工程全阶段实验候选_索引|GF10 金融工程全阶段实验候选索引]]
- GF08-01 风险指标任务建模为 workload。
- GF08-02 回测任务进入队列。
- GF08-03 pricing task 的延迟和失败记录。
- GF08-04 金融 ML 评测记录表。

## 第一轮学习产物

1. 一张 task_type 映射表。
2. 五个 JSON 草图：`risk_metric_task`、`backtest_task`、`pricing_task`、`model_risk_task`、`data_quality_task`。
3. 一张指标分离表：性能指标、质量指标、风险提示。
4. 一个 P03 v0.1 后续接入顺序。

## 检查标准

- [ ] 能说明每个金融 task 来自哪个 F 模块。
- [ ] 能写出 input/output/metrics。
- [ ] 能区分运行指标和金融结果指标。
- [ ] 能说明哪些结果需要人工复核。
- [ ] 能说明还不能写成个人已完成项目成果。

## 暂时不深入

- 不做完整交易平台。
- 不做生产级权限和合规系统。
- 不接商业数据源。
- 不实现完整 P03 金融插件。
- 不把候选 task 写成已完成成果。
