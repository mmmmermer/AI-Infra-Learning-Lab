from __future__ import annotations

from collections.abc import Sequence


Cashflow = tuple[int, float, float]


def coupon_bond_cashflows(
    face_value: float = 100.0,
    coupon_rate: float = 0.05,
    maturity_years: float = 2.0,
    payments_per_year: int = 2,
) -> list[Cashflow]:
    if face_value <= 0 or maturity_years <= 0 or payments_per_year <= 0:
        raise ValueError("face_value, maturity_years and payments_per_year must be positive")

    total_periods = maturity_years * payments_per_year
    if not float(total_periods).is_integer():
        raise ValueError("maturity_years must align with the payment frequency")

    period_count = int(total_periods)
    coupon = face_value * coupon_rate / payments_per_year
    cashflows: list[Cashflow] = []
    for period in range(1, period_count + 1):
        amount = coupon + (face_value if period == period_count else 0.0)
        cashflows.append((period, period / payments_per_year, amount))
    return cashflows


def present_value(
    cashflows: Sequence[Cashflow],
    annual_yield: float,
    payments_per_year: int = 2,
) -> float:
    if payments_per_year <= 0:
        raise ValueError("payments_per_year must be positive")
    if annual_yield <= -payments_per_year:
        raise ValueError("annual_yield makes the periodic discount factor non-positive")

    periodic_yield = annual_yield / payments_per_year
    return sum(
        amount / ((1 + periodic_yield) ** period)
        for period, _time_years, amount in cashflows
    )


def solve_ytm(
    cashflows: Sequence[Cashflow],
    target_price: float,
    payments_per_year: int = 2,
    low: float = -0.20,
    high: float = 1.00,
    tolerance: float = 1e-10,
    max_iterations: int = 200,
) -> float:
    if target_price <= 0:
        raise ValueError("target_price must be positive")
    if low >= high:
        raise ValueError("low must be below high")

    def objective(yield_rate: float) -> float:
        return present_value(cashflows, yield_rate, payments_per_year) - target_price

    f_low = objective(low)
    f_high = objective(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        raise ValueError("YTM root is not bracketed by [low, high]")

    for _ in range(max_iterations):
        midpoint = (low + high) / 2
        f_midpoint = objective(midpoint)
        if abs(f_midpoint) < tolerance or abs(high - low) < tolerance:
            return midpoint
        if f_low * f_midpoint <= 0:
            high = midpoint
        else:
            low = midpoint
            f_low = f_midpoint

    raise RuntimeError("YTM solver did not converge")


def macaulay_duration(
    cashflows: Sequence[Cashflow],
    annual_yield: float,
    payments_per_year: int = 2,
) -> float:
    price = present_value(cashflows, annual_yield, payments_per_year)
    periodic_yield = annual_yield / payments_per_year
    weighted_present_value = sum(
        time_years * amount / ((1 + periodic_yield) ** period)
        for period, time_years, amount in cashflows
    )
    return weighted_present_value / price


def modified_duration(
    cashflows: Sequence[Cashflow],
    annual_yield: float,
    payments_per_year: int = 2,
) -> float:
    return macaulay_duration(cashflows, annual_yield, payments_per_year) / (
        1 + annual_yield / payments_per_year
    )


def convexity(
    cashflows: Sequence[Cashflow],
    annual_yield: float,
    payments_per_year: int = 2,
) -> float:
    price = present_value(cashflows, annual_yield, payments_per_year)
    periodic_yield = annual_yield / payments_per_year
    numerator = sum(
        amount * period * (period + 1) / ((1 + periodic_yield) ** (period + 2))
        for period, _time_years, amount in cashflows
    )
    return numerator / (price * payments_per_year**2)
