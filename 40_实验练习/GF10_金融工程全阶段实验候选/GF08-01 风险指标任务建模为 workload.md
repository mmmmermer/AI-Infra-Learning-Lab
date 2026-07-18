# GF08-01 风险指标任务建模为 workload

> 校订状态：任务契约必须包含不可变输入引用和完整重放信息。`data_source` 只是描述字段，不能替代 artifact URI、hash、as-of time、数据/代码/依赖版本和随机种子。

## 实验定位

本实验把 F02/F03/GF01-GF03 的风险指标计算抽象成 P03 候选 `risk_metric_task`。

它不是实现完整 API，而是设计一个可复现、可排队、可记录、可监控的任务契约：

```text
风险指标实验
-> input_json
-> result_json
-> metrics
-> error_type
-> disclaimer
```

## 前置阅读

- [[10_学习模块/F08_金融工程任务与AI_Workload接口/F08_金融工程任务与AI_Workload接口_适配教材|F08 适配教材]]
- [[50_项目产出/P03_AI_Workload_Platform/03_API与数据契约|P03 API 与数据契约]]
- [[40_实验练习/GF00_金融工程第一阶段实验/GF03-03 VaR 与最大回撤计算|GF03-03 VaR 与最大回撤计算]]

## 实验目标

- [ ] 能把 VaR、volatility、max_drawdown 设计成 `risk_metric_task`。
- [ ] 能区分 input_json、result_json 和 metrics。
- [ ] 能记录 data_source、date_range、confidence_level。
- [ ] 能设计 error_type。
- [ ] 能写明不构成投资建议。

## 任务草图

```json
{
  "schema_version": "finance-task/1.0",
  "task_id": "task_fin_risk_001",
  "task_type": "risk_metric_task",
  "status": "queued",
  "priority": 5,
  "input_json": {
    "data_source": "self-made test data",
    "input_artifact_uri": "artifact://finance/risk/prices.parquet",
    "sha256": "<64-hex-digest>",
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
  "result_json": null,
  "metrics": {},
  "error_type": null
}
```

## 设计步骤

### 步骤 1：定义 input_json

必须包含：

```text
data_source
input_artifact_uri
sha256
as_of_time
data_version
code_ref
dependency_lock_hash
random_seed
asset_list
date_range
frequency
return_field
requested_outputs
parameters
```

### 步骤 2：定义 result_json

```json
{
  "volatility": "calculated",
  "historical_var": "calculated",
  "max_drawdown": "calculated",
  "sample_size": "recorded",
  "limitations": ["sample-based", "no investment advice"],
  "disclaimer": "not investment advice"
}
```

### 步骤 3：定义 performance metrics

```json
{
  "queue_wait_ms": "recorded",
  "task_runtime_ms": "recorded",
  "total_latency_ms": "recorded",
  "data_rows": "recorded"
}
```

注意：`volatility`、`VaR`、`max_drawdown` 不放在 performance metrics 里。

### 步骤 4：定义 error_type

候选：

```text
invalid_input
missing_return_field
insufficient_history
calculation_error
data_quality_error
```

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF08-01 |
| source_experiment | GF03-03 |
| task_type | risk_metric_task |
| input_json |  |
| result_json |  |
| performance_metrics |  |
| error_type_candidates |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 把 VaR 放进 `metrics.task_runtime_ms` 一类字段。
- 不记录 confidence_level。
- 只写 data_source 名称，没有不可变 artifact 和 hash。
- 不记录 as-of time、代码/依赖版本或随机种子。
- 不记录 sample_size。
- 只写结果，不写 input_json。
- 把任务草图说成 P03 已实现。

## 验收标准

- [ ] `risk_metric_task` 字段完整。
- [ ] input/result/performance metrics 分开。
- [ ] error_type 至少有 3 类。
- [ ] 有 limitations 和 disclaimer。
- [ ] 能说明该 task 还只是候选契约，不是已实现功能。
