import pandas as pd

from src.smc_structure import compute_smc_structure


def _make_df(rows: list[dict], start: str = "2026-01-01", freq: str = "1min") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=index)


def _flat_row() -> dict:
    return {"Open": 95.0, "High": 100.0, "Low": 90.0, "Close": 95.0}


def test_choch_then_bos_bullish_with_order_block():
    n = 40
    rows = [_flat_row() for _ in range(n)]

    # Bearish swing structure: lower high, lower low.
    rows[5]["High"] = 120.0   # SH1
    rows[10]["Low"] = 70.0    # SL1
    rows[15]["High"] = 110.0  # SH2 (lower than SH1)
    rows[20]["Low"] = 60.0    # SL2 (lower than SL1)

    # CHoCH: a 3-bar plateau (so none is individually a unique fractal high)
    # with a close that breaks back above SH2 (110).
    for i in (24, 25, 26):
        rows[i]["High"] = 116.0
    rows[24].update({"Open": 108.0, "Close": 115.0, "Low": 107.0})

    # New swing high after the CHoCH.
    rows[30]["High"] = 130.0

    # A deliberate bearish candle inside the order-block lookback window.
    rows[32].update({"Open": 105.0, "Close": 100.0})

    # BOS: another 3-bar plateau breaking back above the new swing high (130).
    for i in (34, 35, 36):
        rows[i]["High"] = 140.0
    rows[34].update({"Open": 125.0, "Close": 135.0})

    df = _make_df(rows)
    structure = compute_smc_structure(df)

    assert structure.trend == "Bullish"
    assert structure.last_event_label == "BOS"
    assert structure.last_event_direction == "bullish"
    assert structure.last_event_level == 130.0
    assert structure.order_block_low == 100.0
    assert structure.order_block_high == 105.0


def test_liquidity_sweep_detected():
    n = 20
    rows = [_flat_row() for _ in range(n)]

    rows[5]["High"] = 120.0  # confirmed swing high

    # Wick above the swing high that closes back below it -- a sweep, not a
    # break. Two tied bars so neither is individually a unique fractal and
    # the original 120 reference survives to be swept.
    rows[10].update({"Open": 112.0, "High": 125.0, "Low": 108.0, "Close": 115.0})
    rows[11]["High"] = 125.0

    df = _make_df(rows)
    structure = compute_smc_structure(df)

    assert structure.sweep_direction == "bearish"
    assert structure.sweep_level == 120.0


def test_too_short_series_returns_unknown():
    rows = [{"Open": 1.0, "High": 1.5, "Low": 0.5, "Close": 1.0} for _ in range(5)]
    df = _make_df(rows)
    structure = compute_smc_structure(df)

    assert structure.trend == "Unknown"
    assert structure.last_event_label is None


def test_empty_df_returns_unknown():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    structure = compute_smc_structure(df)

    assert structure.trend == "Unknown"
