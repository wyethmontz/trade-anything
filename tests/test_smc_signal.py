import pandas as pd

from src.smc_signal import _compute_target, _has_inducement, build_smc_signal
from src.smc_structure import SwingPoint


def _make_df(rows: list[dict], start: str, freq: str) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(rows), freq=freq)
    return pd.DataFrame(rows, index=index)


def _flat_row() -> dict:
    return {"Open": 95.0, "High": 100.0, "Low": 90.0, "Close": 95.0}


def _bearish_zone_df(start: str, freq: str) -> pd.DataFrame:
    """A minimal series whose only confirmed event is a bearish CHoCH with
    order block (90, 95): swing high 110 @5, swing low 80 @10, a bullish
    order-block candle @13, then a close below 80 @15."""
    rows = [_flat_row() for _ in range(20)]
    rows[5]["High"] = 110.0
    rows[10]["Low"] = 80.0
    # The order-block scan starts at the break candle and walks backward, so
    # this needs to be the *immediate* prior candle -- default (flat) candles
    # have Close == Open, which already satisfies "not bearish" and would
    # match first otherwise.
    rows[14].update({"Open": 90.0, "Close": 95.0})
    rows[15].update({"Open": 85.0, "Close": 75.0})
    return _make_df(rows, start, freq)


def _trigger_df(start: str, with_inducement: bool) -> pd.DataFrame:
    """A minimal 1m series with an optional sweep (inducement) at index 5,
    then a retest-and-rejection of the 90-95 zone at index 10."""
    rows = [_flat_row() for _ in range(20)]
    rows[2]["Low"] = 85.0  # confirmed swing low, seeds the sweep target below
    if with_inducement:
        # Two tied bars, not one -- a single-bar wick here would itself become
        # a *new*, more extreme swing low (correctly, per the zigzag rules),
        # which absorbs it into structure instead of sweeping the older 85
        # low. Tied bars aren't individually a unique fractal, so the 85
        # reference survives to actually be swept.
        rows[5]["Low"] = 80.0
        rows[6]["Low"] = 80.0
    rows[10].update({"Open": 91.0, "Close": 88.0})  # pokes into the zone, closes back below it
    return _make_df(rows, start, "1min")


def test_full_chain_fires_sell_setup_with_inducement_and_target():
    bias_df = _bearish_zone_df("2026-01-01", "1h")
    zone_df = _bearish_zone_df("2026-01-01", "15min")  # zone.time = 2026-01-01 03:45
    trigger_df = _trigger_df("2026-01-01 05:00", with_inducement=True)

    since_epoch = (trigger_df.index[0] - pd.Timedelta(minutes=1)).timestamp()
    result = build_smc_signal("GOLDtest", bias_df, zone_df, trigger_df, since_epoch)

    assert result.bias == "bearish"
    assert result.zone is not None
    assert (result.zone.ob_low, result.zone.ob_high) == (90.0, 95.0)
    assert result.message is not None
    assert "SELL SETUP" in result.message
    assert "Entry: ~88.00" in result.message
    assert "Stop: above 97.00" in result.message
    assert "Target: 80.00 (prior swing low)" in result.message
    assert result.triggered_epoch == trigger_df.index[10].timestamp()


def test_no_signal_without_inducement():
    bias_df = _bearish_zone_df("2026-01-01", "1h")
    zone_df = _bearish_zone_df("2026-01-01", "15min")
    trigger_df = _trigger_df("2026-01-01 05:00", with_inducement=False)

    since_epoch = (trigger_df.index[0] - pd.Timedelta(minutes=1)).timestamp()
    result = build_smc_signal("GOLDtest", bias_df, zone_df, trigger_df, since_epoch)

    assert result.message is None
    assert result.zone is not None
    assert result.note == "zone active, no confirmed trigger in scan window"


def test_no_signal_when_scan_window_is_empty():
    bias_df = _bearish_zone_df("2026-01-01", "1h")
    zone_df = _bearish_zone_df("2026-01-01", "15min")
    trigger_df = _trigger_df("2026-01-01 05:00", with_inducement=True)

    since_epoch = trigger_df.index[-1].timestamp()  # already past every candle
    result = build_smc_signal("GOLDtest", bias_df, zone_df, trigger_df, since_epoch)

    assert result.message is None
    assert result.note == "no new M1 candles since last run"


def test_has_inducement_requires_sweep_after_zone_time_and_by_the_retest():
    zone_time = pd.Timestamp("2026-01-01 00:00")
    retest_time = pd.Timestamp("2026-01-01 01:00")
    too_early = [(0, pd.Timestamp("2025-12-31 23:00"), 100.0, "bullish")]
    too_late = [(0, pd.Timestamp("2026-01-01 02:00"), 100.0, "bullish")]
    in_window = [(0, pd.Timestamp("2026-01-01 00:30"), 100.0, "bullish")]

    assert not _has_inducement(zone_time, retest_time, too_early)
    assert not _has_inducement(zone_time, retest_time, too_late)
    assert _has_inducement(zone_time, retest_time, in_window)


def test_compute_target_prefers_swept_level_over_swing_point():
    swept = [(0, pd.Timestamp("2026-01-01"), 90.0, "bearish")]
    swings = [SwingPoint(0, pd.Timestamp("2026-01-01"), 80.0, "low")]

    target, source = _compute_target("bearish", 100.0, swept, swings)
    assert (target, source) == (90.0, "prior swept level")


def test_compute_target_falls_back_to_swing_point_when_no_level_qualifies():
    too_close = [(0, pd.Timestamp("2026-01-01"), 97.0, "bearish")]  # only $3 away, fails MIN_TARGET_GAP
    swings = [SwingPoint(0, pd.Timestamp("2026-01-01"), 80.0, "low")]

    target, source = _compute_target("bearish", 100.0, too_close, swings)
    assert (target, source) == (80.0, "prior swing low")


def test_compute_target_returns_none_when_nothing_qualifies():
    assert _compute_target("bearish", 100.0, [], []) is None
