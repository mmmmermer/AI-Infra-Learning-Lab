# GF04-02 Black-Scholes 定价最小实现

## 实验定位

本实验用最小 Python 函数实现欧式 call/put 的 Black-Scholes 定价。

目标不是推导公式，而是记录输入、输出、假设和限制。本实验的模型价格只用于学习定价流程，不是真实市场报价，也不构成投资建议。

## 前置阅读

- [[10_学习模块/F04_衍生品定价与随机过程导论/F04_衍生品定价与随机过程导论_适配教材|F04 适配教材]]
- [[40_实验练习/GF10_金融工程全阶段实验候选/GF04-01 欧式期权 payoff 图|GF04-01 欧式期权 payoff 图]]

## 实验目标

- [ ] 能写 Black-Scholes 最小定价函数。
- [ ] 能记录 S、K、r、sigma、T、option_type。
- [ ] 能说明主要模型假设。
- [ ] 能说明模型价格不是市场报价。
- [ ] 能映射到 P03 `pricing_task`。

## 测试参数

```yaml
S: 100
K: 100
r: 0.03
sigma: 0.20
T: 1.0
option_type: call
data_source: self-made pricing parameters
not_investment_advice: true
```

## 实验步骤

### 步骤 1：实现函数

```python
from math import exp, log, sqrt, erf

def norm_cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))

def black_scholes_price(S, K, r, sigma, T, option_type="call"):
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

    if option_type == "call":
        return S * norm_cdf(d1) - K * exp(-r * T) * norm_cdf(d2)
    if option_type == "put":
        return K * exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    raise ValueError("option_type must be call or put")
```

### 步骤 2：运行测试

```python
price = black_scholes_price(100, 100, 0.03, 0.20, 1.0, "call")
print(price)
```

### 步骤 3：记录模型假设

至少记录：

```text
European option
constant volatility
constant risk-free rate
no transaction costs
model price only
```

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF04-02 |
| S |  |
| K |  |
| r |  |
| sigma |  |
| T |  |
| option_type |  |
| model_price |  |
| model_assumptions |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- `sigma` 用 20 而不是 0.20。
- `T` 单位不清楚。
- 不说明模型假设。
- 把模型价格写成真实交易报价。

## 验收标准

- [ ] 函数能运行。
- [ ] 输入参数记录完整。
- [ ] 模型假设记录完整。
- [ ] 能写出 P03 `pricing_task` 草图。

## 关联 P03 字段

```json
{
  "task_type": "pricing_task",
  "input_json": {
    "method": "black_scholes",
    "S": 100,
    "K": 100,
    "r": 0.03,
    "sigma": 0.20,
    "T": 1.0,
    "option_type": "call"
  },
  "result_json": {
    "price": "calculated",
    "model_assumptions": "recorded",
    "limitations": ["model price only", "no investment advice"]
  }
}
```
