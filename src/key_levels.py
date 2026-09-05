from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class KeyLevels:
    swing_high: float | None
    swing_low: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    prior_week_high: float | None
    prior_week_low: float | None


def _last_swing_high(df: pd.DataFrame, window: int) -> float | None:
    """Most recent confirmed swing high: a bar whose High is the max within
    `window` bars on both sides. The trailing `window` bars are excluded since
    they can't yet be confirmed as a pivot."""
    highs = df["High"]
    n = len(highs)
    if n < window * 2 + 1:
        return None

    for i in range(n - window - 1, window - 1, -1):
        segment = highs.iloc[i - window : i + window + 1]
        if highs.iloc[i] == segment.max():
            return float(highs.iloc[i])
    return None


def _last_swing_low(df: pd.DataFrame, window: int) -> float | None:
    lows = df["Low"]
    n = len(lows)
    if n < window * 2 + 1:
        return None

    for i in range(n - window - 1, window - 1, -1):
        segment = lows.iloc[i - window : i + window + 1]
        if lows.iloc[i] == segment.min():
            return float(lows.iloc[i])
    return None


def _prior_period_high_low(df: pd.DataFrame, freq: str) -> tuple[float | None, float | None]:
    """High/low of the most recently *completed* period (day or week), excluding
    the still-in-progress current period."""
    if df.empty:
        return None, None

    grouped = df.resample(freq)
    highs = grouped["High"].max().dropna()
    lows = grouped["Low"].min().dropna()
    if len(highs) < 2:
        return None, None

    return float(highs.iloc[-2]), float(lows.iloc[-2])


def compute_key_levels(df: pd.DataFrame, swing_window: int = 5) -> KeyLevels:
    prior_day_high, prior_day_low = _prior_period_high_low(df, "D")
    prior_week_high, prior_week_low = _prior_period_high_low(df, "W")

    return KeyLevels(
        swing_high=_last_swing_high(df, swing_window),
        swing_low=_last_swing_low(df, swing_window),
        prior_day_high=prior_day_high,
        prior_day_low=prior_day_low,
        prior_week_high=prior_week_high,
        prior_week_low=prior_week_low,
    )
