import pandas as pd

from src.key_levels import compute_key_levels, _nearest_round_levels, _round_step_for_price


def _make_df(rows: list[dict], start: str, freq: str) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=index)


def test_swing_high_and_low_are_detected():
    # Gently varying background (no ties) with a clean peak at index 10 and trough at
    # index 20, each confirmed by 5 bars on both sides.
    rows = []
    for i in range(40):
        high = 100.0 + 0.01 * i
        low = 95.0 + 0.01 * i
        if i == 10:
            high = 110.0
        if i == 20:
            low = 80.0
        rows.append({"Open": 98.0, "High": high, "Low": low, "Close": 98.0})

    df = _make_df(rows, "2026-01-01", "1min")
    levels = compute_key_levels(df, swing_window=5)

    assert levels.swing_high == 110.0
    assert levels.swing_low == 80.0


def test_too_short_series_returns_none_swings():
    rows = [{"Open": 1.0, "High": 1.5, "Low": 0.5, "Close": 1.0} for _ in range(5)]
    df = _make_df(rows, "2026-01-01", "1min")
    levels = compute_key_levels(df, swing_window=5)

    assert levels.swing_high is None
    assert levels.swing_low is None


def test_prior_day_and_week_high_low():
    # Three full days of hourly bars: day 1 low range, day 2 wide range, day 3 (today, in progress) narrow.
    rows = []
    for day, (high, low) in enumerate([(105.0, 95.0), (120.0, 80.0), (102.0, 98.0)]):
        for _ in range(24):
            rows.append({"Open": 100.0, "High": high, "Low": low, "Close": 100.0})

    df = _make_df(rows, "2026-01-05", "1h")  # 2026-01-05 is a Monday
    levels = compute_key_levels(df)

    assert levels.prior_day_high == 120.0
    assert levels.prior_day_low == 80.0
    # All three days fall in the same ISO week, which is still in progress -> no prior week yet.
    assert levels.prior_week_high is None
    assert levels.prior_week_low is None


def test_prior_week_high_low_across_week_boundary():
    rows = []
    # Week 1: 2026-01-05 (Mon) through 2026-01-11 (Sun)
    for _ in range(7 * 24):
        rows.append({"Open": 100.0, "High": 130.0, "Low": 70.0, "Close": 100.0})
    # Week 2 (in progress): 2026-01-12 (Mon) onward
    for _ in range(12):
        rows.append({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0})

    df = _make_df(rows, "2026-01-05", "1h")
    levels = compute_key_levels(df)

    assert levels.prior_week_high == 130.0
    assert levels.prior_week_low == 70.0


def test_round_step_scales_with_price_magnitude():
    assert _round_step_for_price(4437.95) == 100.0
    assert _round_step_for_price(95.79) == 1.0
    assert _round_step_for_price(2.53) == 0.1
    assert _round_step_for_price(12345.0) == 500.0


def test_nearest_round_levels_straddle_price():
    below, above = _nearest_round_levels(4437.95, 100.0)
    assert (below, above) == (4400.0, 4500.0)

    below, above = _nearest_round_levels(2.53, 0.1)
    assert (below, above) == (2.5, 2.6)


def test_nearest_round_levels_when_price_is_exactly_on_a_level():
    below, above = _nearest_round_levels(4500.0, 100.0)
    assert (below, above) == (4500.0, 4600.0)


def test_compute_key_levels_includes_round_numbers():
    rows = [{"Open": 194.0, "High": 196.0, "Low": 193.0, "Close": 195.5} for _ in range(10)]
    df = _make_df(rows, "2026-01-01", "1h")
    levels = compute_key_levels(df)

    assert levels.round_level_below == 190.0
    assert levels.round_level_above == 200.0
