from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Direction = Literal["bullish", "bearish"]

FRACTAL_LEGS = 2
ORDER_BLOCK_LOOKBACK = 10
SWEEP_LOOKBACK_BARS = 20  # how recent a sweep must be to still be reported


@dataclass
class SwingPoint:
    index: int
    time: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclass
class StructureEvent:
    index: int
    time: pd.Timestamp
    level: float
    direction: Direction
    label: Literal["BOS", "CHoCH"]
    close: float


@dataclass
class SmcStructure:
    trend: str  # "Bullish", "Bearish", or "Unknown"
    last_event_label: str | None
    last_event_direction: str | None
    last_event_level: float | None
    last_event_time: pd.Timestamp | None
    order_block_low: float | None
    order_block_high: float | None
    sweep_direction: str | None
    sweep_level: float | None
    sweep_time: pd.Timestamp | None


def _find_fractal_swings(df: pd.DataFrame, legs: int) -> list[SwingPoint]:
    """Raw fractal swing points: a bar whose High/Low is the extreme within
    `legs` bars on both sides. Not yet pruned to a clean alternating zigzag."""
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    n = len(df)
    swings: list[SwingPoint] = []
    for i in range(legs, n - legs):
        h_window = highs[i - legs : i + legs + 1]
        l_window = lows[i - legs : i + legs + 1]
        if highs[i] == h_window.max() and (h_window == highs[i]).sum() == 1:
            swings.append(SwingPoint(i, df.index[i], float(highs[i]), "high"))
        if lows[i] == l_window.min() and (l_window == lows[i]).sum() == 1:
            swings.append(SwingPoint(i, df.index[i], float(lows[i]), "low"))
    swings.sort(key=lambda s: s.index)
    return swings


def _zigzag(swings: list[SwingPoint]) -> list[SwingPoint]:
    """Prune raw fractals to a clean alternating high/low sequence, keeping
    the most extreme point of each same-direction run."""
    if not swings:
        return []
    pruned = [swings[0]]
    for s in swings[1:]:
        last = pruned[-1]
        if s.kind == last.kind:
            more_extreme = (s.price >= last.price) if s.kind == "high" else (s.price <= last.price)
            if more_extreme:
                pruned[-1] = s
        else:
            pruned.append(s)
    return pruned


def _order_block(df: pd.DataFrame, break_index: int, direction: Direction) -> tuple[float, float] | None:
    """Last opposite-colored candle before the impulse that caused the break."""
    want_bearish_candle = direction == "bullish"  # bullish break -> OB is the last down-close candle
    lo = max(0, break_index - ORDER_BLOCK_LOOKBACK)
    for i in range(break_index, lo - 1, -1):
        o, c = float(df["Open"].iloc[i]), float(df["Close"].iloc[i])
        is_bearish = c < o
        if is_bearish == want_bearish_candle:
            return (min(o, c), max(o, c))
    return None


def _structure_events(df: pd.DataFrame, zz: list[SwingPoint]) -> list[StructureEvent]:
    """Walk candle closes forward, flagging every BOS / CHoCH against the
    most recently confirmed, not-yet-broken zigzag high/low."""
    events: list[StructureEvent] = []
    if len(zz) < 2:
        return events

    ref_high: SwingPoint | None = None
    ref_low: SwingPoint | None = None
    for s in zz[:2]:
        if s.kind == "high":
            ref_high = s
        else:
            ref_low = s

    trend: Direction | None = None
    zz_i = 2
    start = zz[1].index + 1
    closes = df["Close"].to_numpy()

    for i in range(start, len(df)):
        close = float(closes[i])

        while zz_i < len(zz) and zz[zz_i].index <= i:
            s = zz[zz_i]
            if s.kind == "high":
                ref_high = s
            else:
                ref_low = s
            zz_i += 1

        if ref_high is not None and close > ref_high.price:
            label = "BOS" if trend == "bullish" else "CHoCH"
            events.append(StructureEvent(i, df.index[i], ref_high.price, "bullish", label, close))
            trend = "bullish"
            ref_high = None
        elif ref_low is not None and close < ref_low.price:
            label = "BOS" if trend == "bearish" else "CHoCH"
            events.append(StructureEvent(i, df.index[i], ref_low.price, "bearish", label, close))
            trend = "bearish"
            ref_low = None

    return events


def _liquidity_sweeps(df: pd.DataFrame, zz: list[SwingPoint]) -> list[tuple[int, pd.Timestamp, float, Direction]]:
    """A wick that takes out a swing point but closes back on the other
    side of it — a stop-hunt, often preceding a reversal."""
    sweeps: list[tuple[int, pd.Timestamp, float, Direction]] = []
    active_high: SwingPoint | None = None
    active_low: SwingPoint | None = None
    zz_i = 0
    highs, lows, closes = df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy()

    for i in range(len(df)):
        while zz_i < len(zz) and zz[zz_i].index <= i:
            s = zz[zz_i]
            if s.kind == "high":
                active_high = s
            else:
                active_low = s
            zz_i += 1

        if active_high is not None and highs[i] > active_high.price and closes[i] <= active_high.price:
            sweeps.append((i, df.index[i], active_high.price, "bearish"))
        if active_low is not None and lows[i] < active_low.price and closes[i] >= active_low.price:
            sweeps.append((i, df.index[i], active_low.price, "bullish"))

    return sweeps


def compute_smc_structure(df: pd.DataFrame, fractal_legs: int = FRACTAL_LEGS) -> SmcStructure:
    """Break of structure (BOS), change of character (CHoCH), the order block
    behind the latest break, and any recent liquidity sweep — computed from
    plain OHLC history.

    Informational only, like the other key levels: this does not feed the
    advisor's entry/SL/TP or any guardrail on its own.
    """
    empty = SmcStructure("Unknown", None, None, None, None, None, None, None, None, None)
    if df.empty or len(df) < fractal_legs * 2 + 3:
        return empty

    swings = _find_fractal_swings(df, fractal_legs)
    zz = _zigzag(swings)
    events = _structure_events(df, zz)
    sweeps = _liquidity_sweeps(df, zz)

    trend = "Unknown"
    last_event_label = last_event_direction = None
    last_event_level = None
    last_event_time = None
    order_block_low = order_block_high = None

    if events:
        last = events[-1]
        trend = "Bullish" if last.direction == "bullish" else "Bearish"
        last_event_label = last.label
        last_event_direction = last.direction
        last_event_level = last.level
        last_event_time = last.time
        ob = _order_block(df, last.index, last.direction)
        if ob is not None:
            order_block_low, order_block_high = ob

    sweep_direction = sweep_level = sweep_time = None
    if sweeps:
        cutoff = len(df) - SWEEP_LOOKBACK_BARS
        recent = [s for s in sweeps if s[0] >= cutoff]
        if recent:
            _, sweep_time, sweep_level, sweep_direction = recent[-1]

    return SmcStructure(
        trend=trend,
        last_event_label=last_event_label,
        last_event_direction=last_event_direction,
        last_event_level=last_event_level,
        last_event_time=last_event_time,
        order_block_low=order_block_low,
        order_block_high=order_block_high,
        sweep_direction=sweep_direction,
        sweep_level=sweep_level,
        sweep_time=sweep_time,
    )
