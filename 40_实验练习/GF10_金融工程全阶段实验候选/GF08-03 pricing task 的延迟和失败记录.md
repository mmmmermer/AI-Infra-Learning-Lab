# GF08-03 pricing task 的延迟和失败记录

## 实验定位

本实验把 F04/GF04 的期权定价任务抽象成 P03 候选 `pricing_task`，重点记录：

```text
pricing parameters
-> method
-> simulation_count
-> runtime_ms
-> error_type
-> model_assumptions
-> disclaimer
```

本实验不实现完整 P03，只设计定价 workload 契约。它不输出真实报价，不构成投资建议。

## 前置阅读

- [[10_学习模块/F04_衍生品定价与随机过程导论/F04_衍生品定价与随机过程导论_适配教材|F04 适配教材]]
- [[10_学习模块/F08_金融工程任务与AI_Workload接口/F08_金融工程任务与AI_Workload接口_适配教材|F08 适配教材]]
- [[40_实验练习/GF10_金融工程全阶段实验候选/GF04-03 Monte Carlo 定价最小实现|GF04-03 Monte Carlo 定价最小实现]]

## 实验目标

- [ ] 能设计 `pricing_task` 的 input_json。
- [ ] 能记录 Black-Scholes 和 Monte Carlo 的方法差异。
- [ ] 能记录 simulation_count 和 runtime_ms。
- [ ] 能设计 pricing error_type。
- [ ] 能说明模型价格不是真实市场报价。

## 执行步骤

### 步骤 1：选择定价来源实验

优先从 GF04-02 或 GF04-03 选择一个定价结果，记录方法、参数、随机种子和模拟次数。

### 步骤 2：写 `input_json`

把 `instrument_type`、`option_type`、`S/K/r/sigma/T`、`method`、`simulation_count`、`random_seed` 写入任务输入。

### 步骤 3：写 `result_json` 和 metrics

把模型价格、模型假设、限制说明、`queue_wait_ms`、`task_runtime_ms`、`total_latency_ms` 分开记录。

### 步骤 4：设计失败类型

至少覆盖参数非法、定价方法不支持、模拟失败、数值错误和 worker 错误。

## pricing_task 草图

```json
{
  "task_id": "task_pricing_001",
  "task_type": "pricing_task",
  "status": "queued",
  "input_json": {
    "instrument_type": "european_option",
    "option_type": "call",
    "S": 100,
    "K": 100,
    "r": 0.03,
    "sigma": 0.20,
    "T": 1.0,
    "method": "monte_carlo",
    "simulation_count": 10000,
    "random_seed": 42
  }
}
```

## result_json 设计

```json
{
  "price": "calculated",
  "pricing_method": "monte_carlo",
  "model_assumptions": [
    "European option",
    "constant volatility",
    "constant risk-free rate",
    "no trading costs"
  ],
  "limitations": ["model price only", "not a market quote", "no investment advice"],
  "disclaimer": "not investment advice"
}
```

## metrics 设计

```json
{
  "queue_wait_ms": "recorded",
  "task_runtime_ms": "recorded",
  "total_latency_ms": "recorded",
  "simulation_count": 10000
}
```

`simulation_count` 可以同时作为 input 参数和 workload 规模说明。不要把它当成金融结果。

## error_type 候选

```text
invalid_parameter
unsupported_option_type
unsupported_pricing_method
simulation_error
numerical_error
insufficient_simulation_count
worker_error
```

## 延迟观察设计

如果后续亲手运行 GF04-03，可以记录：

| simulation_count | price | runtime_ms | note |
|---:|---:|---:|---|
| 1000 |  |  |  |
| 10000 |  |  |  |
| 50000 |  |  |  |

观察重点：

```text
simulation_count 增大时，runtime_ms 如何变化？
```

不是观察哪个价格“更适合买卖”。

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF08-03 |
| source_experiment | GF04-03 |
| task_type | pricing_task |
| input_json |  |
| result_json |  |
| metrics |  |
| error_type_candidates |  |
| latency_observation |  |
| model_assumptions |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 不记录 simulation_count。
- 不记录 random_seed。
- 把 runtime_ms 写进 result_json。
- 把模型价格写成真实市场报价。
- 把 pricing_task 草图说成 P03 已实现。

## 验收标准

- [ ] input/result/metrics 分开。
- [ ] error_type 至少 5 类。
- [ ] model_assumptions 和 limitations 完整。
- [ ] 能说明 pricing_task 为什么适合监控 runtime。
- [ ] 明确当前只是候选契约。
