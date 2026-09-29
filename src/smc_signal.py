from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.smc_structure import Direction, SwingPoint, analyze_structure, find_order_block

STOP_BUFFER = 2.0     # points beyond the order block edge
MIN_TARGET_GAP = 5.0  # a candidate target must be at least this many points of profit from entry

Sweep = tuple[int, pd.Timestamp, float, Direction]  # (index, time, level, direction) -- see smc_structure._liquidity_sweeps


@dataclass
class SmcZone:
    direction: Direction
    ob_low: float
    ob_high: float
    time: pd.Timestamp


@dataclass
class SmcSignalResult:
    message: str | None
    bias: Direction | None
    zone: SmcZone | None
    note: str | None            # why nothing fired, for logging -- None when message is set
    triggered_epoch: float | None  # the trigger-candle's time (epoch seconds), for state persistence


def _compute_target(
    direction: Direction, entry: float, sweeps: list[Sweep], swing_points: list[SwingPoint]
) -> tuple[float, str] | None:
    """Find a real liquidity target in the trade direction, at least
    MIN_TARGET_GAP away -- never an arbitrary R-multiple. Preference order:
    1. A level that's already been swept (confirmed real, liquidity is gone).
    2. An untested opposing swing point (a real pivot, just not yet raided).
    Returns None if neither exists -- that means skip the trade, not invent one."""
    if direction == "bearish":
        swept = [s[2] for s in sweeps if s[2] <= entry - MIN_TARGET_GAP]
        if swept:
            return max(swept), "prior swept level"
        swings = [s.price for s in swing_points if s.kind == "low" and s.price <= entry - MIN_TARGET_GAP]
        if swings:
            return max(swings), "prior swing low"
        return None

    swept = [s[2] for s in sweeps if s[2] >= entry + MIN_TARGET_GAP]
    if swept:
        return min(swept), "prior swept level"
    swings = [s.price for s in swing_points if s.kind == "high" and s.price >= entry + MIN_TARGET_GAP]
    if swings:
        return min(swings), "prior swing high"
    return None


def _has_inducement(zone_time: pd.Timestamp, up_to: pd.Timestamp, sweeps: list[Sweep]) -> bool:
    """Inducement (IDM): a minor liquidity sweep since the zone formed, before
    this retest -- confirms price was manipulated into the zone (stops run)
    rather than arriving there in one clean, un-manipulated move."""
    return any(zone_time < s[1] <= up_to for s in sweeps)


def build_smc_signal(
    symbol: str,
    bias_df: pd.DataFrame,
    zone_df: pd.DataFrame,
    trigger_df: pd.DataFrame,
    since_epoch: float | None,
) -> SmcSignalResult:
    """Top-down SMC signal, the way a discretionary trader works a chart:
      - bias_df   (e.g. 1H)  sets the BIAS -- the only direction allowed to trade.
      - zone_df   (e.g. 15m) sets the ZONE -- the most recent order block that
                  agrees with that bias becomes the level to wait for a retest of.
      - trigger_df (e.g. 1m) sets the TRIGGER -- scanned candle by candle (not
                  just the newest one) for every candle since `since_epoch`, so
                  a periodic caller (a bot that runs every N minutes) doesn't
                  miss a setup that formed and resolved between runs.
    A signal only fires when the retest is confirmed AND an inducement sweep
    happened since the zone formed AND a real (not invented) target exists.
    Returns a message only when every condition is met; `note` explains what's
    missing otherwise, for logging. Never raises on missing/empty data.
    """
    _, bias_events, _ = analyze_structure(bias_df)
    bias = bias_events[-1].direction if bias_events else None
    if bias is None:
        return SmcSignalResult(None, None, None, "no H1 bias yet", None)

    zone_swings, zone_events, _ = analyze_structure(zone_df)
    if not zone_events:
        return SmcSignalResult(None, bias, None, "no M15 structure yet", None)
    latest = zone_events[-1]
    if latest.direction != bias:
        return SmcSignalResult(None, bias, None, "M15 zone doesn't agree with H1 bias", None)
    ob = find_order_block(zone_df, latest.index, latest.direction)
    if ob is None:
        return SmcSignalResult(None, bias, None, "M15 zone has no order block", None)
    zone = SmcZone(latest.direction, ob[0], ob[1], latest.time)

    if trigger_df.empty:
        return SmcSignalResult(None, bias, zone, "no M1 data", None)
    _, _, trigger_sweeps = analyze_structure(trigger_df)

    if since_epoch is None:
        scan_df = trigger_df.iloc[[-1]]
    else:
        scan_df = trigger_df[[t.timestamp() > since_epoch for t in trigger_df.index]]
        if scan_df.empty:
            return SmcSignalResult(None, bias, zone, "no new M1 candles since last run", None)

    for ts, row in scan_df.iterrows():
        high, low, close = float(row["High"]), float(row["Low"]), float(row["Close"])

        if zone.direction == "bearish":
            if not (high >= zone.ob_low and close < zone.ob_low):
                continue
            if not _has_inducement(zone.time, ts, trigger_sweeps):
                continue
            entry, stop = close, zone.ob_high + STOP_BUFFER
            found = _compute_target("bearish", entry, trigger_sweeps, zone_swings)
            if found is None:
                continue
            target, source = found
            message = (
                f"SELL SETUP — {symbol}\n"
                f"Order block {zone.ob_low:.2f}-{zone.ob_high:.2f} rejected\n"
                f"Entry: ~{entry:.2f}\n"
                f"Stop: above {stop:.2f}\n"
                f"Target: {target:.2f} ({source})\n"
                f"(H1 bias bearish, confirmed by M15 zone + M1 trigger + inducement)"
            )
            return SmcSignalResult(message, bias, zone, None, ts.timestamp())

        else:
            if not (low <= zone.ob_high and close > zone.ob_high):
                continue
            if not _has_inducement(zone.time, ts, trigger_sweeps):
                continue
            entry, stop = close, zone.ob_low - STOP_BUFFER
            found = _compute_target("bullish", entry, trigger_sweeps, zone_swings)
            if found is None:
                continue
            target, source = found
            message = (
                f"BUY SETUP — {symbol}\n"
                f"Order block {zone.ob_low:.2f}-{zone.ob_high:.2f} held\n"
                f"Entry: ~{entry:.2f}\n"
                f"Stop: below {stop:.2f}\n"
                f"Target: {target:.2f} ({source})\n"
                f"(H1 bias bullish, confirmed by M15 zone + M1 trigger + inducement)"
            )
            return SmcSignalResult(message, bias, zone, None, ts.timestamp())

    return SmcSignalResult(None, bias, zone, "zone active, no confirmed trigger in scan window", None)
