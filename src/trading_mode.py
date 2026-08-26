from __future__ import annotations

# Each mode pairs the candle interval used to compute a signal with how far back
# to look when checking whether an already-open signal has since hit its stop or
# target. `resolve_period` stays within yfinance's lookback limits per interval
# (7d for 1m, 60d for 15m) while comfortably covering how long a signal at that
# granularity should take to resolve.
TRADING_MODES = {
    "scalp": {"period": "1d", "interval": "1m", "resolve_period": "7d", "resolve_interval": "1m"},
    "intraday": {"period": "5d", "interval": "15m", "resolve_period": "60d", "resolve_interval": "15m"},
    "swing": {"period": "1mo", "interval": "1h", "resolve_period": "3mo", "resolve_interval": "1h"},
    "position": {"period": "6mo", "interval": "1d", "resolve_period": "2y", "resolve_interval": "1d"},
}

DEFAULT_TRADING_MODE = "scalp"


def get_trading_mode(key: str) -> dict:
    return TRADING_MODES.get(key, TRADING_MODES[DEFAULT_TRADING_MODE])
