# GF07-05 out-of-sample 与压力测试

## 实验定位

本实验补齐 F07 的最后一块：不要只看一次 train/test 分数，而要观察模型在不同时间段、不同样本环境或轻微参数变化下是否稳定。

它不是为了证明模型有效，而是为了训练风险意识：

```text
一次测试集表现
!=
稳定样本外表现
```

## 前置阅读

- [[10_学习模块/F07_金融机器学习与模型风险/F07_金融机器学习与模型风险_适配教材|F07 金融机器学习与模型风险适配教材]]
- [[40_实验练习/GF10_金融工程全阶段实验候选/GF07-04 模型卡与失败样例记录|GF07-04 模型卡与失败样例记录]]
- [[10_学习模块/M11_科研方法与实验设计/M11_科研方法与实验设计_学习地图|M11 科研方法与实验设计]]

## 实验目标

- [ ] 能解释 out-of-sample 检查的意义。
- [ ] 能做简单时间段切换或滚动切分观察。
- [ ] 能做特征/窗口/样本扰动的压力测试。
- [ ] 能记录指标变化，而不是只保存最好结果。
- [ ] 能把结果写进模型风险说明。

## out-of-sample 的直觉

金融数据环境会变化。模型在早期测试集上表现好，不代表在后续时间段也好。

第一轮不需要复杂统计检验，只做三个问题：

```text
换一个测试时间段，指标是否明显变化？
换一个 rolling window，指标是否明显变化？
去掉一个特征，指标是否明显变化？
```

## 实验方案 A：时间段压力测试

如果数据足够长，可以按时间分成多个测试段：

```text
train: 早期 60%
test_1: 中间 20%
test_2: 后期 20%
```

记录：

| 测试段 | accuracy | precision | recall | F1 | failure_note |
|---|---:|---:|---:|---:|---|
| test_1 |  |  |  |  |  |
| test_2 |  |  |  |  |  |

## 实验方案 B：特征压力测试

比较：

```text
features_v1 = [return_lag_1, return_lag_2, rolling_vol_3]
features_v2 = [return_lag_1, rolling_vol_3]
features_v3 = [return_lag_1]
```

观察指标是否大幅变化。

## 实验方案 C：参数压力测试

比较不同 rolling window：

```text
rolling_vol_3
rolling_vol_5
rolling_vol_10
```

第一轮只记录变化，不做复杂调参。

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF07-05 |
| source_experiment | GF07-02/GF07-04 |
| stress_test_type | time_period / feature_set / parameter |
| baseline_metrics |  |
| test_1_metrics |  |
| test_2_metrics |  |
| feature_set_results |  |
| parameter_results |  |
| stability_note |  |
| failure_analysis |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 只保存表现最好的一组结果。
- 把压力测试当调参竞赛。
- 样本很小却做出稳定性结论。
- 指标变化很大但不写原因。
- 用压力测试结果包装投资能力。

## 验收标准

- [ ] 至少完成一种压力测试方案。
- [ ] 已记录不止一组指标。
- [ ] 已写 stability_note。
- [ ] 已说明样本小或数据自造时不能得出真实市场结论。
- [ ] 能说明压力测试如何进入 M11 实验报告。

## 关联 P03 字段

```json
{
  "task_type": "model_risk_task",
  "result_json": {
    "stress_test": {
      "type": "time_period_or_feature_set_or_parameter",
      "results": "recorded",
      "stability_note": "written by learner"
    },
    "failure_analysis": "recorded",
    "limitations": ["small sample", "no investment advice"]
  }
}
```

## 后续连接

- 连接 M11：压力测试结果可以写入实验设计中的 robustness check。
- 连接 P03：`stress_test` 可以成为 `model_risk_task` 的一部分。
- 连接简历表达：只有亲手运行并记录后，才能说“做过模型风险评估练习”，不能说“已完成可用金融预测模型”。
