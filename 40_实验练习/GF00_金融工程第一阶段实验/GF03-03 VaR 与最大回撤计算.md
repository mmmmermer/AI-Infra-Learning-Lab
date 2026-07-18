# GF03-03 VaR 与最大回撤计算

## 实验定位

本实验承接 GF02-02，把收益率和回撤进一步整理成 F03 的基础风险指标。

核心问题是：

```text
VaR 和 max drawdown 分别描述什么风险？它们如何计算、如何记录、有哪些局限？
```

本实验使用自造测试数据，只用于学习风险指标口径，不代表真实市场风险，不构成投资建议。

## 前置阅读

- [[10_学习模块/F02_Python金融数据与时间序列/F02_Python金融数据与时间序列_适配教材|F02 适配教材]]
- [[10_学习模块/F03_投资组合与风险管理/F03_投资组合与风险管理_学习地图|F03 学习地图]]
- [[40_实验练习/GF00_金融工程第一阶段实验/GF02-02 rolling volatility 与最大回撤|GF02-02 rolling volatility 与最大回撤]]

建议先理解：

- return 是由价格字段计算出来的。
- max drawdown 是历史样本内从 peak 到 trough 的跌幅。
- VaR 是损失分位数口径，不是“最大可能亏损”。

## 实验目标

完成后你应该能：

- [ ] 用收益率序列计算 historical VaR。
- [ ] 说明 VaR 的置信水平和分位数口径。
- [ ] 计算 wealth、drawdown 和 max_drawdown。
- [ ] 区分 VaR 和 max drawdown 的含义。
- [ ] 记录样本范围、频率、收益率口径、置信水平和限制。
- [ ] 写出 P03 `risk_metric_task` 的输入输出草图。

## 测试数据

本实验使用自造日收益率数据。数据故意包含一个较大负收益，用来观察尾部损失和回撤。

```csv
date,symbol,return
2024-01-03,TEST,0.0122
2024-01-04,TEST,-0.0135
2024-01-05,TEST,0.0229
2024-01-08,TEST,0.0109
2024-01-09,TEST,-0.0162
2024-01-10,TEST,0.0040
2024-01-11,TEST,-0.0310
2024-01-12,TEST,0.0180
2024-01-15,TEST,-0.0075
2024-01-16,TEST,0.0065
```

数据说明：

```text
data_source: self-made test data
source_url: none
asset_list: [TEST]
date_range: 2024-01-03 to 2024-01-16
frequency: daily sample
return_method: synthetic returns for workflow practice
point_in_time_note: synthetic data, no real historical availability claim
not_investment_advice: true
```

## 为什么这个实验有意义

F02 已经让你能从价格得到收益率和回撤。F03 要进一步回答：风险该怎么表达？

VaR 和 max drawdown 是两个常见但容易误读的指标。

| 指标 | 关注点 | 回答的问题 | 不能回答什么 |
|---|---|---|---|
| VaR | 单期损失分位数 | 在给定置信水平下，历史样本里较差的一期损失大约多大 | 最坏情况下会亏多少 |
| max drawdown | 路径中的峰值到低点 | 持有路径里经历过多深的下跌 | 下一次最大回撤会是多少 |

它们都是历史样本指标，不是未来保证。

## 知识点与难点

### VaR 的直觉

如果 95% VaR 是 2%，粗略意思是：在这个历史样本和这个计算口径下，较差的 5% 单期收益大约低于 -2%。

更谨慎地说：

```text
VaR 是样本分位数，不是安全线。
```

### VaR 的常见口径

第一轮只做 historical VaR：

```text
historical VaR at 95% confidence = - 5th percentile of returns
```

如果收益率分位数是 -0.02，则 VaR 可以记为 0.02，也可以记为 -0.02。两种写法都有人用，所以实验必须记录 `var_sign_convention`。

本实验采用：

```text
VaR = positive loss number
```

也就是把 -2% 的分位数记录成 2% 的损失。

### 工程痛点

VaR 的工程痛点在于口径太容易混乱：

- 置信水平是 95% 还是 99%？
- 用日收益率、周收益率还是月收益率？
- 输出是正数损失还是负数收益？
- 样本量是否足够？
- 极端值是否来自真实数据还是错误数据？
- 是否把 VaR 当成了最大可能亏损？

所以 VaR 必须和参数一起记录，不能只保存一个数字。

## 实验步骤

### 步骤 1：读取收益率数据

```python
from io import StringIO
import pandas as pd

returns_csv = """date,symbol,return
2024-01-03,TEST,0.0122
2024-01-04,TEST,-0.0135
2024-01-05,TEST,0.0229
2024-01-08,TEST,0.0109
2024-01-09,TEST,-0.0162
2024-01-10,TEST,0.0040
2024-01-11,TEST,-0.0310
2024-01-12,TEST,0.0180
2024-01-15,TEST,-0.0075
2024-01-16,TEST,0.0065
"""

df = pd.read_csv(StringIO(returns_csv))
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").set_index("date")
```

记录：

| 项目 | 记录 |
|---|---|
| return_field | return |
| date_range |  |
| sample_size |  |
| frequency | daily sample |

### 步骤 2：计算 historical VaR

```python
confidence_level = 0.95
tail_probability = 1 - confidence_level

return_quantile = df["return"].quantile(tail_probability)
historical_var = -return_quantile
```

记录：

| 字段 | 记录 |
|---|---|
| confidence_level | 0.95 |
| tail_probability | 0.05 |
| return_quantile |  |
| var_sign_convention | positive loss number |
| historical_var |  |

### 步骤 3：计算 wealth、drawdown 和 max drawdown

```python
wealth = (1 + df["return"]).cumprod()
peak = wealth.cummax()
drawdown = wealth / peak - 1
max_drawdown = drawdown.min()

df["wealth"] = wealth
df["peak"] = peak
df["drawdown"] = drawdown
```

记录：

| 字段 | 记录 |
|---|---|
| wealth_start | 1.0 |
| max_drawdown |  |
| max_drawdown_sign_convention | negative drawdown |
| sample_date_range |  |

### 步骤 4：比较 VaR 和 max drawdown

整理一个风险指标表：

```python
risk_summary = {
    "sample_size": int(df["return"].count()),
    "mean_return": float(df["return"].mean()),
    "return_std": float(df["return"].std()),
    "historical_var_95": float(historical_var),
    "max_drawdown": float(max_drawdown),
}
```

比较：

| 指标 | 本实验含义 |
|---|---|
| `historical_var_95` | 单期收益率分布左尾 5% 附近的损失 |
| `max_drawdown` | 样本路径里从历史峰值到低点的最大下跌 |

### 步骤 5：写限制说明

本实验必须写限制：

```text
limitations:
  - self-made synthetic returns
  - sample size is very small
  - VaR is historical quantile, not a worst-case loss
  - max drawdown is sample-path dependent
  - not investment advice
```

## 实验记录表

### 数据口径记录

| 字段 | 记录 |
|---|---|
| experiment_id | GF03-03 |
| source_module | F03 |
| data_source | self-made test data |
| source_url | none |
| asset_list | TEST |
| date_range | 2024-01-03 to 2024-01-16 |
| frequency | daily sample |
| return_field | return |
| return_method | synthetic returns for workflow practice |
| point_in_time_note | synthetic data, no real historical availability claim |
| not_investment_advice | true |

### 指标口径记录

| 字段 | 记录 |
|---|---|
| confidence_level | 0.95 |
| tail_probability | 0.05 |
| var_method | historical quantile |
| var_sign_convention | positive loss number |
| historical_var |  |
| max_drawdown |  |
| mean_return |  |
| return_std |  |
| limitations | small synthetic sample; no real market conclusion |

## P03 字段映射

候选 task：

```text
p03_task_type: risk_metric_task
```

输入草图：

```json
{
  "task_type": "risk_metric_task",
  "input_json": {
    "data_source": "self-made test data",
    "asset_list": ["TEST"],
    "date_range": ["2024-01-03", "2024-01-16"],
    "return_field": "return",
    "metrics": ["historical_var", "max_drawdown", "mean_return", "return_std"],
    "parameters": {
      "confidence_level": 0.95,
      "var_method": "historical_quantile",
      "var_sign_convention": "positive_loss_number"
    }
  }
}
```

输出草图：

```json
{
  "result_json": {
    "historical_var_95": "<fill_after_run>",
    "max_drawdown": "<fill_after_run>",
    "mean_return": "<fill_after_run>",
    "return_std": "<fill_after_run>",
    "limitations": [
      "self-made synthetic returns",
      "small sample size",
      "not a worst-case loss estimate"
    ],
    "disclaimer": "not investment advice"
  }
}
```

## 常见错误

- 把 VaR 解释成“最大可能亏损”。
- 不记录置信水平。
- 不说明 VaR 是正数损失还是负数收益。
- 用太小样本得出风险结论。
- 把 max drawdown 当作未来风险上限。
- 混用日收益率和月收益率。
- 不记录数据来源和样本时间范围。

## 验收标准

- [ ] 能计算 historical VaR。
- [ ] 能说明 confidence level 和 tail probability。
- [ ] 能说明 VaR 的符号约定。
- [ ] 能计算 wealth、drawdown 和 max_drawdown。
- [ ] 能区分 VaR 和 max drawdown。
- [ ] 能填写指标口径记录表。
- [ ] 能写出 P03 `risk_metric_task` 输入输出草图。
- [ ] 能明确说明结果不构成投资建议。

## 下一步

完成本实验后，可以进入：

- GF03-01 两资产组合风险收益曲线。
- Q01 金融数据分析与风险指标实验候选。
- Q02 投资组合与风险管理实验候选。

当前仍不创建 Q01/Q02 工作台。先积累实验记录和解释能力，再进入项目工作台。
