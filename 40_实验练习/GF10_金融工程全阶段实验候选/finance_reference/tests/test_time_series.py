import pandas as pd
import pytest

from finance_reference.time_series import (
    calculate_grouped_returns,
    clean_price_data,
    make_direction_labels,
    split_with_gap,
)


def test_cleaning_preserves_different_symbols_on_the_same_date():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"],
            "symbol": ["A", "B", "A", "B"],
            "adjusted_close": [100.0, 50.0, 110.0, 55.0],
        }
    )

    cleaned = clean_price_data(frame)

    assert len(cleaned.xs(pd.Timestamp("2024-01-02"), level="date")) == 2
    assert set(cleaned.index.get_level_values("symbol")) == {"A", "B"}


def test_returns_do_not_cross_asset_boundaries():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03"],
            "symbol": ["A", "A", "B", "B"],
            "adjusted_close": [100.0, 110.0, 50.0, 55.0],
        }
    )

    result = calculate_grouped_returns(clean_price_data(frame))

    assert pd.isna(result.loc[("A", pd.Timestamp("2024-01-02")), "return"])
    assert pd.isna(result.loc[("B", pd.Timestamp("2024-01-02")), "return"])
    assert result.loc[("A", pd.Timestamp("2024-01-03")), "return"] == pytest.approx(0.10)
    assert result.loc[("B", pd.Timestamp("2024-01-03")), "return"] == pytest.approx(0.10)


def test_direction_labels_drop_unknown_future_before_casting():
    index = pd.date_range("2024-01-01", periods=5, freq="D")
    returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.04], index=index)

    dataset = make_direction_labels(returns, horizon=1)

    assert len(dataset) == 4
    assert dataset.index.max() == index[-2]
    assert dataset["label"].tolist() == [0, 1, 0, 1]


def test_temporal_split_keeps_gaps_and_final_holdout():
    index = pd.date_range("2024-01-01", periods=30, freq="D")
    dataset = pd.DataFrame({"feature": range(30)}, index=index)

    split = split_with_gap(dataset, horizon=2)

    assert index.get_loc(split.validation.index.min()) - index.get_loc(split.train.index.max()) > 2
    assert index.get_loc(split.test.index.min()) - index.get_loc(split.validation.index.max()) > 2


def test_gf07_fixture_keeps_three_nonempty_sets_and_two_train_classes():
    dates = pd.bdate_range("2024-01-02", periods=60)
    return_pattern = [0.01, -0.008, 0.012, -0.006, 0.004, -0.011, 0.009, -0.003]
    prices = [100.0]
    for index in range(1, len(dates)):
        period_return = return_pattern[(index - 1) % len(return_pattern)]
        prices.append(prices[-1] * (1 + period_return))

    frame = pd.DataFrame({"adjusted_close": prices}, index=dates)
    frame["return"] = frame["adjusted_close"].pct_change()
    frame["future_return"] = frame["return"].shift(-1)
    frame = frame.dropna(subset=["future_return"]).copy()
    frame["label"] = (frame["future_return"] > 0).astype("int8")
    frame["return_lag_1"] = frame["return"].shift(1)
    frame["return_lag_2"] = frame["return"].shift(2)
    frame["rolling_vol_3"] = frame["return"].rolling(3).std().shift(1)
    dataset = frame.dropna(
        subset=["return_lag_1", "return_lag_2", "rolling_vol_3"]
    )

    split = split_with_gap(dataset, horizon=1)

    assert not split.train.empty
    assert not split.validation.empty
    assert not split.test.empty
    assert split.train["label"].nunique() == 2

    from sklearn.linear_model import LogisticRegression

    features = ["return_lag_1", "return_lag_2", "rolling_vol_3"]
    model = LogisticRegression(solver="liblinear", random_state=20260711)
    model.fit(split.train[features], split.train["label"])

    assert len(model.predict(split.validation[features])) == len(split.validation)
    assert len(model.predict(split.test[features])) == len(split.test)
