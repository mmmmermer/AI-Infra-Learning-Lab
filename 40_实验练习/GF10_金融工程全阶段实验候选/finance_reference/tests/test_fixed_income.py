import pytest

from finance_reference.fixed_income import (
    convexity,
    coupon_bond_cashflows,
    macaulay_duration,
    modified_duration,
    present_value,
    solve_ytm,
)


def test_par_bond_prices_at_face_value_when_coupon_equals_yield():
    cashflows = coupon_bond_cashflows(100.0, 0.05, 5.0, payments_per_year=2)

    assert present_value(cashflows, 0.05, payments_per_year=2) == pytest.approx(100.0)


def test_ytm_solver_recovers_positive_and_negative_yields():
    coupon_cashflows = coupon_bond_cashflows(100.0, 0.05, 2.0, payments_per_year=2)
    coupon_price = present_value(coupon_cashflows, 0.04, payments_per_year=2)
    assert solve_ytm(coupon_cashflows, coupon_price, payments_per_year=2) == pytest.approx(
        0.04, abs=1e-8
    )

    zero_coupon = coupon_bond_cashflows(100.0, 0.0, 1.0, payments_per_year=1)
    premium_price = present_value(zero_coupon, -0.01, payments_per_year=1)
    assert solve_ytm(
        zero_coupon,
        premium_price,
        payments_per_year=1,
        low=-0.50,
        high=0.50,
    ) == pytest.approx(-0.01, abs=1e-8)


def test_ytm_solver_rejects_unbracketed_root():
    cashflows = coupon_bond_cashflows(100.0, 0.05, 2.0, payments_per_year=2)

    with pytest.raises(ValueError, match="not bracketed"):
        solve_ytm(cashflows, target_price=1_000.0, payments_per_year=2, low=0.0, high=0.5)


def test_duration_and_convexity_match_small_finite_difference():
    cashflows = coupon_bond_cashflows(100.0, 0.05, 5.0, payments_per_year=2)
    annual_yield = 0.04
    shock = 1e-4
    price = present_value(cashflows, annual_yield, payments_per_year=2)
    price_up = present_value(cashflows, annual_yield + shock, payments_per_year=2)
    price_down = present_value(cashflows, annual_yield - shock, payments_per_year=2)

    effective_duration = (price_down - price_up) / (2 * price * shock)
    effective_convexity = (price_down + price_up - 2 * price) / (price * shock**2)

    assert macaulay_duration(cashflows, annual_yield, 2) > modified_duration(
        cashflows, annual_yield, 2
    )
    assert modified_duration(cashflows, annual_yield, 2) == pytest.approx(
        effective_duration, rel=1e-6
    )
    assert convexity(cashflows, annual_yield, 2) == pytest.approx(
        effective_convexity, rel=1e-5
    )
