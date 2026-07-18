from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


REQUIRED_PRICE_COLUMNS = {"date", "symbol", "adjusted_close"}


def clean_price_data(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_PRICE_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    cleaned = frame.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="raise")
    cleaned = cleaned.sort_values(["symbol", "date"])
    cleaned = cleaned.drop_duplicates(subset=["symbol", "date"], keep="last")
    cleaned = cleaned.dropna(subset=["adjusted_close"])

    if (cleaned["adjusted_close"] <= 0).any():
        raise ValueError("adjusted_close must be positive")

    return cleaned.set_index(["symbol", "date"]).sort_index()


def calculate_grouped_returns(cleaned: pd.DataFrame) -> pd.DataFrame:
    if list(cleaned.index.names) != ["symbol", "date"]:
        raise ValueError("cleaned data must use a (symbol, date) MultiIndex")

    result = cleaned.sort_index().copy()
    result["return"] = result.groupby(level="symbol")["adjusted_close"].pct_change(
        fill_method=None
    )
    return result


def make_direction_labels(returns: pd.Series, horizon: int = 1) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise ValueError("returns must use a DatetimeIndex")

    dataset = pd.DataFrame({"return": returns.sort_index()})
    dataset["future_return"] = dataset["return"].shift(-horizon)
    dataset = dataset.dropna(subset=["future_return"]).copy()
    dataset["label"] = (dataset["future_return"] > 0).astype("int8")
    return dataset


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_with_gap(
    dataset: pd.DataFrame,
    horizon: int = 1,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
) -> TemporalSplit:
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1:
        raise ValueError("ratios must be between 0 and 1")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio + validation_ratio must be below 1")

    ordered = dataset.sort_index()
    train_end = int(len(ordered) * train_ratio)
    validation_end = int(len(ordered) * (train_ratio + validation_ratio))

    train = ordered.iloc[:train_end]
    validation = ordered.iloc[train_end + horizon : validation_end]
    test = ordered.iloc[validation_end + horizon :]
    if train.empty or validation.empty or test.empty:
        raise ValueError("dataset is too small for the requested split and gap")

    return TemporalSplit(train=train, validation=validation, test=test)
