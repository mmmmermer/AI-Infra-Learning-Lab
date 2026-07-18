# GF02-02 rolling volatility 与最大回撤

## 实验定位

本实验承接 GF02-01。GF02-01 解决“数据能不能用”，GF02-02 解决“清洗后的价格序列如何转成基础风险观察指标”。

本实验仍使用自造测试数据，只训练计算流程和记录习惯，不代表真实市场结论，不构成投资建议。

```text
cleaned_price_series
-> return
-> rolling volatility
-> wealth / peak / drawdown
-> max_drawdown
-> risk_metric_task 草图
```

## 前置阅读

- [[10_学习模块/F02_Python金融数据与时间序列/F02_Python金融数据与时间序列_适配教材|F02 适配教材]]
- [[40_实验练习/GF00_金融工程第一阶段实验/GF02-01 金融时间序列清洗|GF02-01 金融时间序列清洗]]
- pandas window operations

重点阅读 F02 适配教材：

- 第 4 章：收益率和对数收益率。
- 第 5 章：rolling window 和滚动波动率。
- 第 6 章：drawdown 和 max drawdown。

## 实验目标

完成后你应该能：

- [ ] 从 cleaned price 计算简单收益率。
- [ ] 说明第一行 return 为什么为空。
- [ ] 选择一个 rolling window，并记录窗口口径。
- [ ] 计算 rolling volatility。
- [ ] 计算 wealth、peak、drawdown 和 max_drawdown。
- [ ] 说明 rolling volatility 和 max_drawdown 的区别。
- [ ] 把结果映射成 P03 `risk_metric_task` 字段。

## 测试数据

本实验直接使用 GF02-01 清洗后可以得到的简化数据。这里为了自包含，重新给出 cleaned 数据：

```csv
date,symbol,adjusted_close
2024-01-02,TEST,98.50
2024-01-03,TEST,99.70
2024-01-04,TEST,98.35
2024-01-05,TEST,100.60
2024-01-08,TEST,101.70
2024-01-09,TEST,100.05
```

数据说明：

```text
data_source: self-made test data
source_url: none
asset_list: [TEST]
date_range: 2024-01-02 to 2024-01-09
frequency: daily sample, not real trading calendar
price_field: adjusted_close
point_in_time_note: synthetic data, no real historical availability claim
not_investment_advice: true
```

## 为什么这个实验有意义

金融数据处理的第一步是清洗，第二步通常就是把价格转成风险可以使用的指标。

三个核心指标分别回答不同问题：

| 指标 | 回答的问题 | 常见误读 |
|---|---|---|
| return | 每期相对前一期变化多少 | 把价格差当收益率 |
| rolling volatility | 最近一段时间波动大不大 | 忘记窗口大小和是否年化 |
| max drawdown | 样本内从峰值最多跌了多少 | 当成未来最大亏损预测 |

这个实验的价值不是算出一个数字，而是学会记录口径：窗口是多少、数据范围是什么、是否年化、使用哪个价格字段、结果只能描述哪个样本。

## 实验步骤

### 步骤 1：读取 cleaned price series

```python
from io import StringIO
import pandas as pd

cleaned_csv = """date,symbol,adjusted_close
2024-01-02,TEST,98.50
2024-01-03,TEST,99.70
2024-01-04,TEST,98.35
2024-01-05,TEST,100.60
2024-01-08,TEST,101.70
2024-01-09,TEST,100.05
"""

df = pd.read_csv(StringIO(cleaned_csv))
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").set_index("date")
```

记录：

| 项目 | 记录 |
|---|---|
| 输入是否来自 GF02-01 cleaned output |  |
| price_field | adjusted_close |
| final_rows |  |
| date_range |  |

### 步骤 2：计算简单收益率

```python
df["return"] = df["adjusted_close"].pct_change()
```

观察：

- 第一行 return 是空值，因为没有前一期价格。
- return 的数量通常比价格数量少 1。
- 后续指标要说明是否删除第一行空值。

记录：

| 日期 | adjusted_close | return |
|---|---:|---:|
| 2024-01-02 | 98.50 |  |
| 2024-01-03 | 99.70 |  |
| 2024-01-04 | 98.35 |  |

### 步骤 3：选择 rolling window

本实验样本很小，所以使用 3 期窗口演示。

```python
window_size = 3
annualized = False
```

这不是推荐真实金融分析使用 3 日窗口，而是为了让你能看懂 rolling 计算。真实日频数据常见 20、60、252 等窗口，但必须结合问题说明。

记录：

| 字段 | 记录 |
|---|---|
| window_size | 3 |
| min_periods | 默认等于 window_size |
| annualized_or_not | false |
| frequency | daily sample |

### 步骤 4：计算 rolling volatility

```python
df["rolling_volatility"] = df["return"].rolling(window=window_size).std()
```

观察：

- 前几行 rolling volatility 为空，是因为窗口还没有积累足够样本。
- rolling volatility 是收益率的滚动标准差，不是价格的滚动标准差。
- 如果年化，需要乘以 `sqrt(252)`，但本实验不年化。

### 步骤 5：计算 wealth、peak 和 drawdown

```python
returns = df["return"].dropna()
wealth = (1 + returns).cumprod()
peak = wealth.cummax()
drawdown = wealth / peak - 1

df.loc[returns.index, "wealth"] = wealth
df.loc[returns.index, "peak"] = peak
df.loc[returns.index, "drawdown"] = drawdown

max_drawdown = drawdown.min()
```

解释：

| 字段 | 含义 |
|---|---|
| `wealth` | 从 1 开始的累计净值 |
| `peak` | 到当前为止的历史最高累计净值 |
| `drawdown` | 当前净值相对历史最高点的跌幅 |
| `max_drawdown` | 样本内最深回撤 |

### 步骤 6：整理输出表

```python
output = df[
    [
        "symbol",
        "adjusted_close",
        "return",
        "rolling_volatility",
        "wealth",
        "peak",
        "drawdown",
    ]
]
```

输出表至少要能回答：

- 使用哪个价格字段？
- 收益率怎么算？
- rolling window 是多少？
- 是否年化？
- max_drawdown 是哪个样本范围内的历史结果？

## 观察指标

| 指标 | 记录方式 | 解释边界 |
|---|---|---|
| `mean_return` | `return.mean()` | 样本平均收益，不代表未来收益 |
| `return_std` | `return.std()` | 全样本收益率标准差 |
| `rolling_volatility` | rolling std | 受窗口大小影响 |
| `max_drawdown` | drawdown min | 样本内历史最大回撤 |
| `window_size` | 手动记录 | 不同窗口不可直接混比 |
| `annualized_or_not` | 手动记录 | 必须说明是否年化 |

## 实验记录表

### 数据口径记录

| 字段 | 记录 |
|---|---|
| experiment_id | GF02-02 |
| source_module | F02/F03 |
| data_source | self-made test data |
| source_url | none |
| asset_list | TEST |
| date_range | 2024-01-02 to 2024-01-09 |
| frequency | daily sample |
| price_field | adjusted_close |
| return_method | pct_change |
| point_in_time_note | synthetic data, no real historical availability claim |
| not_investment_advice | true |

### 指标口径记录

| 字段 | 记录 |
|---|---|
| window_size | 3 |
| annualized_or_not | false |
| min_periods | default |
| mean_return |  |
| return_std |  |
| max_drawdown |  |
| limitations | small synthetic sample; no market conclusion |

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
    "date_range": ["2024-01-02", "2024-01-09"],
    "price_field": "adjusted_close",
    "return_method": "pct_change",
    "metrics": ["return", "rolling_volatility", "max_drawdown"],
    "parameters": {
      "window_size": 3,
      "annualized": false
    }
  }
}
```

输出草图：

```json
{
  "result_json": {
    "mean_return": "<fill_after_run>",
    "return_std": "<fill_after_run>",
    "max_drawdown": "<fill_after_run>",
    "rolling_volatility_series": "<table_or_artifact_ref>",
    "limitations": "small synthetic sample; no real market conclusion",
    "disclaimer": "not investment advice"
  }
}
```

## 常见错误

- 用价格计算 rolling std，却写成收益率波动率。
- 不记录窗口大小。
- 不说明是否年化。
- 忘记第一行 return 为空。
- 把 max_drawdown 解释成未来可能最大亏损。
- 用很小样本得出市场判断。
- 没有记录 `price_field`，导致后续无法复现。

## 验收标准

- [ ] 能从 cleaned price 计算 return。
- [ ] 能解释第一行 return 为空。
- [ ] 能计算 rolling volatility。
- [ ] 能说明 window_size 的影响。
- [ ] 能计算 wealth、peak、drawdown 和 max_drawdown。
- [ ] 能填写数据口径和指标口径记录表。
- [ ] 能写出 P03 `risk_metric_task` 草图。
- [ ] 能说明所有结果只描述样本，不构成投资建议。

## 下一步

完成本实验后，可以进入：

- GF03-03 VaR 与最大回撤计算。
- GF03-01 两资产组合风险收益曲线。
- Q01 金融数据分析与风险指标实验候选。

当前仍不创建 Q01 工作台。先完成至少两个 GF 实验，并保留代码、记录表和解释，再考虑项目工作台。
