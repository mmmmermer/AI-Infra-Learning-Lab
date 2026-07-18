# GF04-01 欧式期权 payoff 图

## 实验定位

本实验是 F04 的入口练习：先理解 call/put 到期 payoff，再谈定价模型。

核心流程：

```text
S_T range
-> call_payoff
-> put_payoff
-> payoff table / chart
-> payoff_note
-> P03 pricing_task 前置理解
```

本实验不做真实期权报价，不做投资建议。

## 前置阅读

- [[10_学习模块/F04_衍生品定价与随机过程导论/F04_衍生品定价与随机过程导论_适配教材|F04 适配教材]]

## 实验目标

- [ ] 能计算欧式 call payoff。
- [ ] 能计算欧式 put payoff。
- [ ] 能画出或记录 payoff 表。
- [ ] 能说明 payoff 和 price 的区别。

## 测试参数

```yaml
K: 100
S_T_range: [60, 80, 100, 120, 140]
option_types: [call, put]
data_source: self-made payoff grid
not_investment_advice: true
```

## 实验步骤

### 步骤 1：定义 payoff

```python
def call_payoff(s_t, k):
    return max(s_t - k, 0)

def put_payoff(s_t, k):
    return max(k - s_t, 0)
```

### 步骤 2：生成表格

```python
import pandas as pd

K = 100
s_values = [60, 80, 100, 120, 140]

df = pd.DataFrame({"S_T": s_values})
df["call_payoff"] = df["S_T"].apply(lambda x: call_payoff(x, K))
df["put_payoff"] = df["S_T"].apply(lambda x: put_payoff(x, K))

print(df)
```

### 步骤 3：画图

```python
ax = df.plot(x="S_T", y=["call_payoff", "put_payoff"], marker="o")
ax.set_title("European option payoff")
```

如果不画图，也必须保存 payoff 表和解释。

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF04-01 |
| K |  |
| S_T_range |  |
| call_payoff_table |  |
| put_payoff_table |  |
| payoff_note |  |
| price_vs_payoff_note |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 把 payoff 当作今天的期权价格。
- call/put 公式写反。
- 不记录 strike。
- 把 payoff 图解释成交易建议。

## 验收标准

- [ ] call/put payoff 表正确。
- [ ] 能说明 strike 的作用。
- [ ] 能说明 payoff 和 price 的区别。
- [ ] 明确不构成投资建议。

## 关联 P03 字段

```json
{
  "task_type": "pricing_task",
  "input_json": {
    "instrument_type": "european_option",
    "option_type": "call_or_put",
    "K": 100,
    "S_T_range": [60, 80, 100, 120, 140]
  },
  "result_json": {
    "payoff_table": "recorded",
    "price_vs_payoff_note": "recorded",
    "limitations": ["payoff only", "not a model price", "no investment advice"]
  }
}
```
