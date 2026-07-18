# GF04-03 Monte Carlo 定价最小实现

## 实验定位

本实验用 Monte Carlo 模拟估计欧式期权价格，并记录 `seed`、`simulation_count` 和 `runtime_ms`。

它连接 F04 和 F08/P03：

```text
simulation_count
-> runtime_ms
-> pricing_task
-> M05/M08 workload 指标
```

## 前置阅读

- [[10_学习模块/F04_衍生品定价与随机过程导论/F04_衍生品定价与随机过程导论_适配教材|F04 适配教材]]
- [[40_实验练习/GF10_金融工程全阶段实验候选/GF04-02 Black-Scholes 定价最小实现|GF04-02 Black-Scholes 定价最小实现]]
- [[10_学习模块/F08_金融工程任务与AI_Workload接口/F08_金融工程任务与AI_Workload接口_适配教材|F08 适配教材]]

## 实验目标

- [ ] 能用随机模拟生成到期价格。
- [ ] 能计算折现 payoff 平均值。
- [ ] 能记录随机种子和模拟次数。
- [ ] 能记录运行时间。
- [ ] 能说明 Monte Carlo 结果有随机误差。
- [ ] 能映射到 `pricing_task`。

## 实验步骤

### 步骤 1：实现 Monte Carlo 定价

```python
import math
import random
import time

def monte_carlo_option_price(S, K, r, sigma, T, option_type="call", simulation_count=10000, seed=42):
    random.seed(seed)
    start = time.perf_counter()
    payoffs = []

    for _ in range(simulation_count):
        z = random.gauss(0, 1)
        s_t = S * math.exp((r - 0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * z)
        if option_type == "call":
            payoffs.append(max(s_t - K, 0))
        elif option_type == "put":
            payoffs.append(max(K - s_t, 0))
        else:
            raise ValueError("option_type must be call or put")

    price = math.exp(-r * T) * (sum(payoffs) / simulation_count)
    runtime_ms = (time.perf_counter() - start) * 1000
    return price, runtime_ms
```

### 步骤 2：运行不同模拟次数

```python
for n in [1000, 10000, 50000]:
    price, runtime_ms = monte_carlo_option_price(
        S=100, K=100, r=0.03, sigma=0.20, T=1.0,
        option_type="call", simulation_count=n, seed=42
    )
    print(n, price, runtime_ms)
```

### 步骤 3：记录观察

观察：

```text
simulation_count 增大时，估计通常更稳定，但 runtime_ms 也会上升。
```

不要把一次模拟结果写成真实市场价格。

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF04-03 |
| S |  |
| K |  |
| r |  |
| sigma |  |
| T |  |
| option_type |  |
| seed |  |
| simulation_count |  |
| monte_carlo_price |  |
| runtime_ms |  |
| error_note |  |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 不记录 seed。
- 不记录 simulation_count。
- 不记录 runtime_ms。
- 用太小样本做结论。
- 把 Monte Carlo 结果和真实报价混淆。

## 验收标准

- [ ] 能运行 Monte Carlo 定价。
- [ ] 至少比较两个 simulation_count。
- [ ] 已记录 seed 和 runtime_ms。
- [ ] 能说明随机误差。
- [ ] 能写 pricing_task 字段。

## 关联 P03 字段

```json
{
  "task_type": "pricing_task",
  "input_json": {
    "method": "monte_carlo",
    "S": 100,
    "K": 100,
    "r": 0.03,
    "sigma": 0.20,
    "T": 1.0,
    "option_type": "call",
    "simulation_count": 10000,
    "random_seed": 42
  },
  "result_json": {
    "price": "calculated",
    "model_assumptions": "recorded",
    "limitations": ["Monte Carlo estimate", "model price only", "no investment advice"]
  },
  "metrics": {
    "runtime_ms": "recorded",
    "simulation_count": 10000
  }
}
```
