# GF05-01 债券定价和 YTM

> 校订状态：本实验支持付息频率和负收益率根区间，YTM 求解必须先验证括根并在不收敛时显式报错。最小实现假设结算日在付息日，因此 accrued interest=0、clean price=dirty price；非付息日结算和 day-count 需另行实现并记录。

## 实验定位

本实验把 F05 的现金流、折现和 YTM 直觉落到可运行练习中。

核心流程：

```text
cashflow schedule
-> present value
-> target price
-> solve YTM
-> fixed_income_task 草图
```

本实验使用教学参数，不是真实债券报价，也不做真实债券投资建议。

## 前置阅读

- [[10_学习模块/F05_固定收益与利率基础/F05_固定收益与利率基础_适配教材|F05 适配教材]]

## 实验目标

- [ ] 能列出 coupon bond 现金流。
- [ ] 能计算现值。
- [ ] 能用数值方法反解 YTM。
- [ ] 能记录 coupon、maturity、yield、price。
- [ ] 能说明 coupon rate 和 YTM 不同。

## 实验步骤

### 步骤 1：生成现金流

```python
def coupon_bond_cashflows(
    face_value=100.0,
    coupon_rate=0.05,
    maturity_years=2.0,
    payments_per_year=2,
):
    if face_value <= 0 or maturity_years <= 0 or payments_per_year <= 0:
        raise ValueError("face_value, maturity_years and payments_per_year must be positive")

    total_periods = maturity_years * payments_per_year
    if not float(total_periods).is_integer():
        raise ValueError("maturity_years must align with the payment frequency")

    total_periods = int(total_periods)
    coupon = face_value * coupon_rate / payments_per_year
    cashflows = []
    for period in range(1, total_periods + 1):
        cf = coupon
        if period == total_periods:
            cf += face_value
        cashflows.append((period, period / payments_per_year, cf))
    return cashflows
```

### 步骤 2：计算现值

```python
def present_value(cashflows, annual_yield, payments_per_year=2):
    if annual_yield <= -payments_per_year:
        raise ValueError("annual_yield makes the periodic discount factor non-positive")
    periodic_yield = annual_yield / payments_per_year
    return sum(
        cf / ((1 + periodic_yield) ** period)
        for period, _time_years, cf in cashflows
    )

cashflows = coupon_bond_cashflows(100, 0.05, 2, payments_per_year=2)
dirty_price = present_value(cashflows, 0.04, payments_per_year=2)
accrued_interest = 0.0  # settlement is assumed to be exactly on a coupon date
clean_price = dirty_price - accrued_interest
assert abs(present_value(cashflows, 0.05, 2) - 100.0) < 1e-10
print(cashflows, dirty_price, clean_price)
```

### 步骤 3：反解 YTM

```python
def solve_ytm(
    cashflows,
    target_price,
    payments_per_year=2,
    low=-0.20,
    high=1.00,
    tol=1e-10,
    max_iter=200,
):
    if target_price <= 0:
        raise ValueError("target_price must be positive")

    def objective(yield_rate):
        return present_value(cashflows, yield_rate, payments_per_year) - target_price

    f_low = objective(low)
    f_high = objective(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        raise ValueError("YTM root is not bracketed by [low, high]")

    for _ in range(max_iter):
        mid = (low + high) / 2
        f_mid = objective(mid)
        if abs(f_mid) < tol or abs(high - low) < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
        else:
            low = mid
            f_low = f_mid

    raise RuntimeError("YTM solver did not converge")

ytm = solve_ytm(cashflows, target_price=dirty_price, payments_per_year=2)
assert abs(ytm - 0.04) < 1e-8
print(ytm)
```

## 记录表

| 字段 | 本次记录 |
|---|---|
| experiment_id | GF05-01 |
| face_value |  |
| coupon_rate |  |
| maturity |  |
| payment_frequency | semiannual / 2 |
| cashflow_schedule |  |
| yield_rate |  |
| present_value |  |
| dirty_price / clean_price |  |
| accrued_interest | 0（付息日结算假设） |
| day_count / settlement_assumption | coupon-date teaching assumption |
| target_price |  |
| solved_ytm |  |
| solver_method | bisection |
| limitations |  |
| not_investment_advice | true |

## 常见错误

- 忘记最后一期本金。
- 把 coupon rate 当 YTM。
- 不记录 payment_frequency。
- 不记录求解方法和误差。
- 没有验证 `[low, high]` 是否括住根，或不收敛时仍返回结果。
- 暴露 payment_frequency 却仍按年付息生成现金流。
- 把付息日结算的 clean=dirty 结论推广到非付息日。

## 验收标准

- [ ] 现金流表正确。
- [ ] 现值计算能运行。
- [ ] YTM 反解能运行。
- [ ] coupon rate 等于 YTM 时，付息日价格能通过 par=100 已知答案测试。
- [ ] 不括根和不收敛路径会显式报错。
- [ ] 能解释 coupon rate 和 yield 的区别。

## 关联 P03 字段

```json
{
  "task_type": "fixed_income_task",
  "input_json": {
    "face_value": 100,
    "coupon_rate": 0.05,
    "maturity": 2,
    "payment_frequency": "annual",
    "target_price": "recorded"
  },
  "result_json": {
    "cashflow_schedule": "calculated",
    "present_value": "calculated",
    "ytm": "calculated",
    "limitations": ["learning example", "no investment advice"]
  }
}
```
