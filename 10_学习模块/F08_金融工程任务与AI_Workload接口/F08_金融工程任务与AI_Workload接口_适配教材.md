# F08 金融工程任务与 AI Workload 接口适配教材

<!-- textbook-content: default=design-note -->

> 2026-07-10 校订：金融 task 只有数据源名称和日期范围时无法重放。统一契约必须保存不可变 artifact URI、SHA-256、as-of time、数据/代码/依赖版本和随机种子；输入中的结果清单统一命名为 `requested_outputs`，避免与系统 performance metrics 混淆。

## 编写说明

F08 是金融工程第二主线和 AI Infra 主线的接口模块。它不新增很多金融理论，也不创建完整金融平台，而是回答一个工程问题：

```text
已经学过的金融数据、风险指标、回测、模型风险实验，
如何变成 P03 可以创建、排队、执行、查询、记录、监控和复核的 workload？
```

第一轮只做任务抽象、字段设计和记录规范，不实现完整 P03 金融插件，不创建 X02 工作台，不把候选 task 写成已完成项目成果。

对应入口：

- [[10_学习模块/F08_金融工程任务与AI_Workload接口/F08_金融工程任务与AI_Workload接口_学习地图|F08 学习地图]]
- [[20_资料库/模块资料索引/F08_金融工程任务与AI_Workload接口_资料索引|F08 资料索引]]
- [[50_项目产出/P03_AI_Workload_Platform/03_API与数据契约|P03 API 与数据契约]]
- [[40_实验练习/GF10_金融工程全阶段实验候选/GF10_金融工程全阶段实验候选_索引|GF10 金融工程全阶段实验候选索引]]

## 开始之前

| 项目 | 要求 |
|---|---|
| 目标读者 | 已做过至少一种金融计算实验、需要学习如何把实验结果设计成平台任务契约的学习者 |
| 先修知识 | 完成 F02/F03，并至少选修 F06 或 F07；理解 M02 请求/响应、M05 队列状态和 M08 指标分层 |
| 前置诊断 | 打开 P03 `p03_service/app/models.py`，核对当前允许的 `task_type`；若仍不含金融任务，后文只能按设计说明阅读 |
| 版本边界 | 当前边界为 P03 v0.3.1：只注册 `mock_rag/mock_agent/simulated_inference/rag_retrieval`。schema、代码、数据和依赖均需版本化，金融 task 尚不可执行 |
| 学习产物 | 一份候选 task schema、数据 artifact/哈希清单、错误分类、幂等与 owner-scope 说明，以及激活条件清单 |
| 完成口径 | 能进行设计评审和 JSON 口径核对，不等于平台已实现；未注册金融 task 不得写成端到端教程或项目成果 |
| 建议用时 | 作者侧初步估计 4-6 小时；先读公共信封与证据边界，再按已完成的金融实验选择一个 task 草图 |

## 第一轮学习边界

要学：

- 金融任务为什么要从 notebook/script 抽象成 task。
- `task_type`、`input_json`、`result_json`、`metrics`、`error_type` 的分工。
- `risk_metric_task`、`portfolio_task`、`backtest_task`、`model_risk_task`、`data_quality_task` 的最小字段。
- performance metrics、financial metrics、quality metrics 的区别。
- `data_source`、`data_version`、`point_in_time_note`、`review_status`、`disclaimer` 为什么重要。
- 如何连接 M05 队列、M06 状态持久化、M08 监控、M11 实验记录和 P03 项目契约。

暂时不学：

- 完整交易平台。
- 生产级权限和合规系统。
- 商业金融数据接入。
- 真实投资建议。
- 完整 P03 金融插件实现。
- 自动化标注平台或多人审核系统。

## 本模块最值得理解的难点

F08 的难点不是 JSON 字段多，而是“同一个任务结果里混着三类完全不同的东西”：工程性能、金融计算结果、质量/风险复核。

| 难点 | 为什么难 | 工程痛点 | 后续影响 |
|---|---|---|---|
| 任务字段混杂 | latency、VaR、review_status 不是同一类指标 | 全塞进 result_json 后不可查询 | P03 metrics 和报告会混乱 |
| 金融结果需要口径 | VaR、回撤、回测结果依赖样本和参数 | 只保存数字无法复现 | Q 项目和面试解释站不住 |
| 数据时点很重要 | 金融数据可能修订或复权 | 不记录 data_version 会产生未来信息风险 | F06/F07 可信度下降 |
| task 状态影响复盘 | failed/retrying/cancelled 都有含义 | 失败只写日志，无法统计错误类型 | M06/M08 无法接上 |
| review 字段不能替代结果 | 人工复核是质量说明，不是计算结果 | 把 review_score 当性能指标会误导 | M11/RQ 记录失真 |
| disclaimer 不是装饰 | 金融任务容易被误读成建议 | 缺少边界会污染简历和项目表达 | 就业材料风险变高 |

学习 F08 的核心习惯是：

```text
每个 task 都必须能回答：输入是什么、怎么算、结果是什么、运行多慢、失败怎么记、质量如何复核、不能说明什么。
```

## 一条贯通学习线

F08 的学习对象不是某个金融公式，而是“金融实验如何工程化”。第一轮按这条线学习：

```text
一个 notebook/script
-> 明确输入参数
-> 明确计算函数
-> 明确结果字段
-> 明确运行指标
-> 明确失败类型
-> 明确复核和限制
-> 变成 P03 task
```

如果一个金融实验不能走完这条线，它就还只是个人学习脚本，不能进入项目表达。

最小例子：

| 脚本阶段 | task 化以后 |
|---|---|
| 手动读取价格列表 | `input_json.data_source/date_range/fields` |
| 计算收益率和 VaR | `result_json.risk_metrics` |
| print 输出结果 | 可查询的 `result_json` |
| 运行多久不知道 | `metrics.task_runtime_ms` |
| 出错直接中断 | `status=failed` + `error_type` |
| 没有说明边界 | `limitations` + `disclaimer` |

## 可迁移的原则

1. 任务契约要把工程字段和金融字段分开。`status`、`latency_ms`、`error_type` 属于工程执行；VaR、price、signal、risk_metrics 属于金融结果；review 和 disclaimer 属于质量边界。
2. 金融 task 必须可复现。输入数据版本、参数、时间范围、随机种子、代码版本和结果摘要都要能追溯。
3. P03 只承接任务，不替你证明金融结论。平台能记录、调度、监控金融计算，但不能把未验证结果变成投资能力。

## 踩坑现场

> 你把 `risk_metrics`、`latency_ms`、`review_status` 全塞进一个 `result_json`，短期省事，后期无法筛选失败任务、比较延迟或生成报告。更稳的做法是保留统一 task envelope，再把金融结果和复核信息放在清晰的子字段里。

## 第 1 章：金融脚本为什么要变成 task

### 1.1 本章解决什么问题

在 notebook 里运行一次 VaR、回测或模型评估，只是学习实验。要进入 P03，就必须变成可追踪任务：

```text
POST create task
-> status queued/running/succeeded/failed
-> worker execute
-> result_json
-> metrics
-> review record
-> GET /tasks/{task_id}
```

### 1.2 工程直觉

脚本只关心“这次能不能跑出结果”。task 还要关心：

- 谁提交的。
- 输入参数是什么。
- 任务是否排队。
- worker 是否执行成功。
- 执行耗时多久。
- 失败属于什么类型。
- 结果有没有质量/风险说明。
- 未来能不能复现。

可以把脚本和 task 的区别理解成：

```text
script = 一次性动作
task = 可追踪、可恢复、可审计的动作记录
```

这就是为什么 F08 必须连接 M05/M06/M08：金融计算本身只是业务逻辑，队列、状态、持久化和监控才让它变成工程系统的一部分。

### 1.3 和 P03 的关系

P03 v0.3.1 已实现并验证的主线是 mock workload 与 `rag_retrieval`。F08 只定义金融 task 的
候选扩展，当前 API 会拒绝这些未注册 `task_type`，不能写成 v0.3.1 已实现能力：

```text
P03 v0.3.1 task lifecycle 与 server-owned principal
-> 同一套 task lifecycle
-> 金融 task_type 候选
-> 后续 X02 再实现
```

### 1.4 常见错误

- 直接把 notebook 输出当作 task result。
- 只保存结果，不保存 input_json。
- 只记录金融指标，不记录 runtime/error。
- 把候选 task 写成 P03 已实现功能。
- 把金融计算输出写成投资建议。

### 1.5 小练习

选一个最小风险指标脚本，回答：

| 问题 | 你的回答 |
|---|---|
| 输入数据来自哪里？ |  |
| 哪些参数会影响结果？ |  |
| 输出哪些金融指标？ |  |
| 运行指标记录什么？ |  |
| 失败可能是什么类型？ |  |
| 结果不能说明什么？ | 不构成投资建议 |

只有这张表能填完整，才进入后面的 JSON schema。

## 第 2 章：统一 Task Envelope

### 2.1 本章解决什么问题

不同金融任务可以有不同的输入输出，但外层任务信封应该尽量统一。

```json
{
  "schema_version": "finance-task/1.0",
  "task_id": "task_fin_001",
  "task_type": "risk_metric_task",
  "status": "queued",
  "priority": 5,
  "input_json": {
    "input_artifact": {
      "uri": "artifact://finance/demo/prices.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "requested_outputs": []
  },
  "result_json": null,
  "metrics": {},
  "error_type": null,
  "created_at": "2026-06-30T10:00:00Z"
}
```

`artifact://` 只是本库约定的内部 locator，不是互联网标准，也不自动代表内容不可变。
`digest` 必须对下载后实际执行的精确字节计算；Parquet 就哈希文件字节，JSON 则必须先固定
编码和规范化方式。读取方同时校验 `size_bytes`、`media_type` 和 digest。哈希只能证明取到
的字节与声明一致，不能替代来源授权、访问控制、数据许可或 point-in-time 检查。

所有跨系统时间戳使用带 `Z` 或明确 UTC offset 的 RFC 3339 字符串。无时区的
`2026-06-30T10:00:00` 在跨主机任务中属于不完整契约。

### 2.2 字段分工

| 字段 | 作用 | 不应该放什么 |
|---|---|---|
| `input_json` | 不可变输入、hash、时点、版本、seed 和请求输出 | 运行耗时、最终指标 |
| `result_json` | 金融计算或模型评估结果 | queue_wait、worker_utilization |
| `metrics` | 工程运行指标 | VaR、accuracy、投资结论 |
| `error_type` | 失败分类 | 长篇失败复盘 |
| `review_status` | 人工复核状态 | 替代模型或金融指标 |
| `disclaimer` | 使用边界 | 空泛宣传 |

### 2.3 状态流

第一轮沿用 P03/M06：

```text
pending -> queued
queued -> running
running -> succeeded
running -> failed
running -> retrying
retrying -> queued
```

其中 `retrying` 只能由一次可重试的 `running` 尝试进入，随后重新排队；它不是
`succeeded` 或 `failed` 之后的通用下一状态。`cancelled` 只保留在数据库枚举中，当前 P03
没有取消 API，也没有任何合法迁移能到达该状态。

金融 task 不需要发明新状态。只有人工复核可以额外用：

```text
review_status: pending / reviewed / needs_revision
```

状态的意义不是“好看”，而是让失败和延迟可以被追踪：

| 状态 | 含义 | 金融任务例子 |
|---|---|---|
| pending | 已创建但还没进入队列 | 用户提交了 VaR 任务 |
| queued | 等待 worker | 队列里前面还有 Monte Carlo 任务 |
| running | worker 正在执行 | 正在读取数据并计算指标 |
| succeeded | 执行成功 | result_json 已写入 |
| failed | 执行失败 | 缺字段、数据为空、求解失败 |
| retrying | 准备重试 | 临时下载失败或 worker 中断 |
| cancelled | 预留但当前不可达 | 当前 P03 没有取消 API，不能把输入错误记作取消 |

没有状态流，F08 就会退回 notebook：你只能知道最后有没有输出，看不到中间发生了什么。

### 2.4 常见错误

- 在 `status` 里写业务结论。
- `failed` 后没有 `error_type`。
- `result_json` 里没有 limitations。
- `metrics` 里混入金融结果。

### 2.5 最小校验规则

每个金融 task 进入 P03 前，至少做这些校验：

```text
task_type 是否在允许列表
input_json 是否包含必要字段
date_range 是否合法
input_artifact 的 uri / media_type / size_bytes / digest 是否完整
code_ref / dependency_lock_hash / random_seed 是否可重放
requested_outputs 是否只描述请求的金融输出
metrics 是否只放工程性能指标
result_json 是否包含 limitations/disclaimer
error_type 是否来自候选枚举
```

这些校验不需要一开始做成复杂权限系统，但要先写进 task 契约。

## 第 3 章：risk_metric_task 和 portfolio_task

### 3.1 来源

这两个 task 承接：

- F02 金融时间序列。
- F03 风险指标和组合风险。
- GF01/GF02/GF03 实验。

### 3.2 risk_metric_task

```json
{
  "task_type": "risk_metric_task",
  "input_json": {
    "data_source": "self-made test data",
    "input_artifact": {
      "uri": "artifact://finance/risk/prices.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "asset_list": ["TEST"],
    "date_range": ["2024-01-02", "2024-01-15"],
    "frequency": "daily sample",
    "return_field": "return",
    "requested_outputs": ["volatility", "historical_var", "max_drawdown"],
    "parameters": {
      "confidence_level": 0.95,
      "var_method": "historical"
    }
  },
  "result_json": {
    "volatility": "calculated",
    "historical_var": "calculated",
    "max_drawdown": "calculated",
    "limitations": ["sample-based", "no investment advice"],
    "disclaimer": "not investment advice"
  },
  "metrics": {
    "task_runtime_ms": "recorded",
    "data_rows": "recorded"
  }
}
```

### 3.3 portfolio_task

```json
{
  "task_type": "portfolio_task",
  "input_json": {
    "input_artifact": {
      "uri": "artifact://finance/portfolio/returns.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "asset_order": ["A", "B"],
    "weights": [0.6, 0.4],
    "constraints": {
      "long_only": true,
      "weight_sum": 1.0
    },
    "requested_outputs": ["portfolio_return", "portfolio_volatility"]
  },
  "result_json": {
    "portfolio_return": "calculated",
    "portfolio_volatility": "calculated",
    "covariance_matrix": "calculated",
    "limitations": ["sample-based", "no investment advice"]
  }
}
```

### 3.4 工程痛点

`portfolio_task` 必须记录 `asset_order`。否则权重 `[0.6, 0.4]` 对应的是 A/B 还是 B/A 会不清楚。

`risk_metric_task` 必须记录 `confidence_level`、`frequency` 和 `var_method`。否则 VaR 数字没有解释力。

更细一点看，风险指标 task 的核心不是算出一个 VaR，而是能解释这个数字来自哪里：

```text
return_field
date_range
frequency
confidence_level
var_method
sample_size
limitations
```

如果这些字段缺失，`historical_var = -0.032` 只是一个孤立数字。它不能进入报告，也不能进入简历表达。

### 3.5 检查标准

- [ ] 能区分 input、result 和 metrics。
- [ ] 能说明 VaR 为什么必须记录置信水平。
- [ ] 能说明 portfolio_task 为什么必须记录资产顺序。

## 第 4 章：backtest_task 和 model_risk_task

### 4.1 backtest_task 来源

承接 F06/GF06：

```text
price
-> signal
-> position
-> strategy_return
-> cost
-> leakage_check
```

### 4.2 backtest_task 草图

```json
{
  "task_type": "backtest_task",
  "input_json": {
    "data_source": "self-made test data",
    "input_artifact": {
      "uri": "artifact://finance/backtest/prices.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "asset_list": ["TEST"],
    "price_fields": ["adjusted_open", "adjusted_close"],
    "signal_rule": {
      "type": "moving_average",
      "window": 3
    },
    "execution_assumption": {
      "decision_time": "close",
      "fill_time": "next_open",
      "return_interval": "same_day_open_to_close",
      "exit_time": "same_day_close",
      "overnight_position": 0,
      "position_shift": 1,
      "rebalancing_frequency": "daily sample"
    },
    "cost_model": {
      "type": "fixed_per_side_notional_rate",
      "cost_rate_per_side": 0.001,
      "turnover_definition": "entry_abs_position_plus_exit_abs_position"
    }
  },
  "result_json": {
    "equity_curve": "calculated",
    "max_drawdown": "calculated",
    "turnover": "calculated",
    "leakage_check": {
      "position_shift": {"status": "pass|fail|not_run", "evidence": "artifact-or-test-id"},
      "decision_fill_return_interval": {"status": "recorded|missing", "evidence": "report-field"},
      "universe_policy": {"status": "recorded|missing", "value": "point_in_time|other"}
    },
    "limitations": ["simplified backtest", "no investment advice"]
  },
  "metrics": {
    "task_runtime_ms": "recorded",
    "queue_wait_ms": "recorded",
    "data_rows": "recorded"
  }
}
```

### 4.3 model_risk_task 来源

承接 F07/GF07：

```text
label
-> features
-> split
-> baseline
-> model
-> metrics
-> leakage_check
-> model_card
```

### 4.4 model_risk_task 草图

```json
{
  "task_type": "model_risk_task",
  "input_json": {
    "input_artifact": {
      "uri": "artifact://finance/model/features.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "label_definition": "next_period_return_positive",
    "label_information_interval": "(close_t, close_t_plus_horizon]",
    "horizon": 2,
    "horizon_unit": "trading_session",
    "feature_list": ["return_lag_1", "return_lag_2", "rolling_vol_3"],
    "required_columns": ["label", "return_lag_1", "return_lag_2", "rolling_vol_3"],
    "nan_policy": "drop required rows after feature and label construction",
    "split_rule": {
      "type": "time_ordered",
      "shuffle": false,
      "gap": 2,
      "label_overlap_check": "required"
    },
    "baseline_rule": "majority_class",
    "threshold_selection_set": "validation",
    "final_test_policy": "frozen and used once after configuration freeze",
    "model_config": {
      "model_type": "logistic_regression"
    }
  },
  "result_json": {
    "baseline_metrics": "calculated",
    "model_metrics": "calculated",
    "confusion_matrix": "calculated",
    "failure_examples": "recorded",
    "leakage_check": {
      "future_return_in_features": {"status": "pass|fail|not_run", "evidence": "test-id"},
      "scaler_fit_scope": {"status": "train|other|not_run", "evidence": "pipeline-config"},
      "label_overlap": {"status": "pass|fail|not_run", "evidence": "test-id"},
      "final_test_access_count": "record actual integer"
    },
    "model_card": "recorded",
    "limitations": ["learning sample", "no investment advice"]
  }
}
```

### 4.5 工程痛点

`backtest_task` 不能只保存最终收益。必须保存成本、换手、泄漏检查和限制。

`model_risk_task` 不能只保存 accuracy。必须保存 baseline、失败样例、泄漏检查和模型卡。

这里最容易犯的错是“结果导向”：看到回测收益或模型准确率，就急着写项目成果。F08 的标准相反，先看记录是否完整：

| 任务 | 结果数字之前必须先有 |
|---|---|
| backtest_task | signal 生成规则、position_shift、成本模型、泄漏检查 |
| model_risk_task | 标签定义、时间切分、baseline、特征列表、失败样例 |

没有这些前置记录，结果数字越漂亮越危险。

## 第 5 章：data_quality_task 和 finance_rag_query

### 5.1 data_quality_task

承接 F02/GF02：

```json
{
  "task_type": "data_quality_task",
  "input_json": {
    "data_source": "self-made test data",
    "input_artifact": {
      "uri": "artifact://finance/quality/prices.parquet",
      "media_type": "application/vnd.apache.parquet",
      "size_bytes": 12345,
      "digest": "sha256:<64-hex-digest>"
    },
    "as_of_time": "2024-01-15T23:59:59Z",
    "data_version": "synthetic-v1",
    "code_ref": "git:<commit>",
    "dependency_lock_hash": "sha256:<lock-hash>",
    "random_seed": 20260710,
    "source_url": null,
    "asset_list": ["TEST"],
    "date_range": ["2024-01-02", "2024-01-15"],
    "fields": ["adjusted_close"],
    "frequency": "daily sample"
  },
  "result_json": {
    "missing_ratio": {"adjusted_close": 0.0},
    "duplicate_dates": 0,
    "final_rows": "calculated",
    "quality_flags": [],
    "point_in_time_note": "synthetic data, not applicable",
    "limitations": ["synthetic data"]
  }
}
```

### 5.2 finance_rag_query

承接 M03/M12/P03。第一轮只作为候选 task，不实现完整金融 RAG：

```json
{
  "task_type": "finance_rag_query",
  "input_json": {
    "document_id": "demo_doc",
    "query": "请列出公告中的主要风险提示。",
    "top_k": 3
  },
  "result_json": {
    "answer": "mock answer",
    "citations": ["demo_doc#chunk_01"],
    "has_citation": true,
    "risk_note": "requires manual review",
    "disclaimer": "not investment advice"
  },
  "metrics": {
    "retrieval_ms": "recorded",
    "generation_ms": "recorded",
    "total_latency_ms": "recorded"
  }
}
```

`tenant_id`、`user_id`、`permission_groups` 和 `allowed_groups` 等安全字段禁止出现在
`input_json`。API 从已认证主体生成 server-owned principal，提交 task 时保存 tenant/user/
permission snapshot；worker 必须在排序和进入 prompt 之前按该 snapshot 过滤。客户端传入
同名字段必须返回 `422`，不能把它当作可选覆盖值。

### 5.3 工程痛点

金融 RAG 的 `has_citation` 只是最低要求，不代表结论正确。必须允许 `review_status` 和 `risk_note` 存在。

`data_quality_task` 的价值不是“清洗成功”，而是让后续风险指标、回测、模型评估知道数据是否可靠。

对于金融文档任务，F08 还要继承 M12 的边界：

```text
citations 说明答案有来源
review_status 说明是否人工看过
risk_note 说明可能仍需谨慎
disclaimer 说明不是投资建议
```

这四个字段不能互相替代。尤其是 `has_citation=true` 不等于“结论一定正确”，它只说明回答引用了某些片段。

## 第 6 章：三类指标必须分开

### 6.1 performance metrics

用于 M08 监控：

```text
queue_wait_ms
task_runtime_ms
total_latency_ms
error_rate
worker_utilization
data_rows
```

### 6.2 financial/result metrics

用于金融结果：

```text
volatility
VaR
max_drawdown
portfolio_volatility
turnover
model_accuracy
confusion_matrix
```

### 6.3 quality/review metrics

用于 M11/ReviewRecord：

```text
review_status
rubric_score
unsupported_claim_count
leakage_flags
quality_flags
failure_examples
```

### 6.4 常见错误

- 把 `accuracy` 放进 performance metrics。
- 把 `runtime_ms` 当作金融结果质量。
- 把 `review_status=reviewed` 当作结果正确。
- 没有 `disclaimer`。

### 6.5 三类指标的报告位置

后续写实验报告时，可以这样分层：

| 报告区域 | 放什么 | 不放什么 |
|---|---|---|
| 工程运行 | latency、queue_wait、runtime、error_rate | VaR、收益、准确率 |
| 金融结果 | 波动率、VaR、回撤、回测指标、模型指标 | worker utilization |
| 质量复核 | 数据缺失、泄漏检查、citation、人工复核 | 绝对投资判断 |

这张表也是 P03/M08/M11 的连接点：M08 负责工程指标，F03/F06/F07 负责金融指标，M11 负责实验设计和结论边界。

## 第 7 章：接口 walkthrough：从风险脚本到候选 task

### 7.1 本章解决什么问题

前面几章分别讲字段，这一章把它们串起来。假设你已经在 GF03 里写过一个最小风险指标脚本：

```text
输入：一组日收益率
计算：波动率、历史 VaR、最大回撤
输出：三个风险指标
```

F08 要做的是把它变成候选接口说明。本章没有服务端 schema、worker 或查询结果，因此是
design-note 演练，不是可运行 tutorial；只有实现并通过 contract test 后才能改名为完整流程。

### 7.2 第一步：确定输入

```json
{
  "data_source": "self-made test data",
  "input_artifact": {
    "uri": "artifact://finance/risk/prices.parquet",
    "media_type": "application/vnd.apache.parquet",
    "size_bytes": 12345,
    "digest": "sha256:<64-hex-digest>"
  },
  "as_of_time": "2024-01-15T23:59:59Z",
  "data_version": "synthetic-v1",
  "code_ref": "git:<commit>",
  "dependency_lock_hash": "sha256:<lock-hash>",
  "random_seed": 20260710,
  "asset_list": ["TEST"],
  "date_range": ["2024-01-02", "2024-01-15"],
  "frequency": "daily sample",
  "return_field": "return",
  "parameters": {
    "confidence_level": 0.95,
    "var_method": "historical"
  },
  "requested_outputs": ["volatility", "historical_var", "max_drawdown"]
}
```

输入要能复现。不要只写“用某股票数据”，要写清数据来源、范围、字段和参数。

### 7.3 第二步：确定执行流程

```text
validate input
-> load returns
-> compute volatility
-> compute historical VaR
-> compute max drawdown
-> write result_json
-> write metrics
```

这一步对应 worker。未来 M06 会负责状态持久化，M05 会负责排队和调度，M08 会观察耗时和错误率。

### 7.4 第三步：确定输出和指标

```json
{
  "result_json": {
    "risk_metrics": {
      "volatility": "calculated",
      "historical_var": "calculated",
      "max_drawdown": "calculated"
    },
    "limitations": [
      "small sample",
      "historical estimate only",
      "no investment advice"
    ],
    "disclaimer": "not investment advice"
  },
  "metrics": {
    "queue_wait_ms": "recorded",
    "task_runtime_ms": "recorded",
    "data_rows": "recorded"
  }
}
```

注意：`volatility` 是金融结果，`task_runtime_ms` 是工程指标。它们都重要，但不能混在同一层含义里。

### 7.5 第四步：确定失败路径

| 失败场景 | error_type | 应该记录 |
|---|---|---|
| 缺少 return 字段 | `missing_required_field` | 字段名、输入摘要 |
| date_range 为空 | `empty_dataset` | date_range、data_source |
| confidence_level 非法 | `invalid_parameter` | 参数值 |
| worker 中断 | `worker_error` | 日志摘要和重试次数 |

失败记录不是丢脸，而是工程能力的一部分。没有失败分类，后续 M08 只能看到“有些任务挂了”，无法知道应该优化数据校验、worker 还是队列。

### 7.6 验收标准

- [ ] 能把 GF03 风险指标脚本拆成 input、result、metrics、error_type。
- [ ] 能解释每个字段为什么需要。
- [ ] 能说明 M05/M06/M08 分别接管哪一部分。
- [ ] 能说明这个 task 仍然不构成投资建议。

## 第 8 章：F08 到 X02 的激活条件

<!-- textbook-content: type=appendix -->

### 8.1 当前不创建 X02

X02 是“金融工程任务 Workload 接入 P03”的候选项目，不是当前已完成项目。

只有满足以下条件，才考虑创建工作台：

- P03 v0.3.1 reference 的 owner scope、状态、outbox/worker 和 metrics 契约保持通过。
- 金融 task_type 已在单一 JSON Schema/服务端模型中注册，并有正反 contract tests。
- 至少一个 GF 金融实验被亲手运行。
- 有真实记录表、参数、输出和失败分析。
- 能把该实验稳定映射成 task schema。
- 能说明不构成投资建议。

### 8.2 推荐接入顺序

```text
data_quality_task
-> risk_metric_task
-> portfolio_task
-> backtest_task
-> model_risk_task
-> finance_rag_query
```

原因：

- data_quality_task 和 risk_metric_task 最简单，最适合验证字段契约。
- backtest_task 和 model_risk_task 更复杂，需要 F06/F07 亲手实验记录。
- finance_rag_query 涉及文本证据、引用和人工复核，后续结合 M12/P03 再推进。

## 学习检查

- [ ] 能写出统一 Task Envelope。
- [ ] 能区分 input_json、result_json、metrics、review_status。
- [ ] 能设计 `risk_metric_task`。
- [ ] 能设计 `backtest_task`。
- [ ] 能设计 `model_risk_task`。
- [ ] 能说明 performance metrics、financial metrics、quality metrics 的区别。
- [ ] 能说明 X02 现在仍是候选，不是已完成项目。

## 正文主张与来源映射

| 正文主张 | 权威依据 | 本教材采用的简化 | 不能推出什么 |
|---|---|---|---|
| Task Envelope 应由可验证 Schema 约束 | [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core) | 当前先给候选 JSON，后续再落 schema 文件 | 示例 JSON 不等于已启用服务端校验 |
| 跨系统时间必须带时区语义 | [RFC 3339](https://datatracker.ietf.org/doc/html/rfc3339) | 统一使用 UTC `Z` 或显式 offset | 不能用本地无时区时间排序分布式事件 |
| provenance 要描述实体、活动和责任主体 | [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) | 先记录数据、代码、依赖和执行关系 | 一个 URI 或 hash 不是完整 provenance |
| artifact descriptor 至少绑定媒体类型、大小和 digest | [OCI Image Specification Descriptor](https://specs.opencontainers.org/image-spec/descriptor/) | 借用 descriptor 思路，不声称兼容 OCI registry | digest 不证明许可、正确性或授权 |
| 构建/执行来源应可验证和可追踪 | [SLSA Provenance](https://slsa.dev/spec/v1.1/provenance) | 用于设计 reference provenance 字段 | 当前学习任务未达到 SLSA 等级声明 |

## 暂时不要深入

- 不实现完整金融插件。
- 不创建 X02 工作台。
- 不写投资建议。
- 不接商业数据源。
- 不做生产级权限系统。
- 不把候选 JSON 草图写成 P03 已实现功能。
