"""Throwaway probe: compare candidate Yahoo Finance tickers for Brent Crude against
each other to see which tracks a broker cash/CFD quote most closely. Not part of the
app; delete after use.
"""
from __future__ import annotations

import yfinance as yf

CANDIDATES = ["BZ=F", "BZT=F", "^SGICBRB", "CL=F"]

for symbol in CANDIDATES:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m")
        if hist.empty:
            hist = ticker.history(period="5d", interval="1d")
        if hist.empty:
            print(f"{symbol}: no data returned")
            continue
        last = hist.iloc[-1]
        print(f"{symbol}: last_close={last['Close']:.4f} as_of={hist.index[-1]}")
        fast = ticker.fast_info
        print(f"{symbol}: fast_info last_price={getattr(fast, 'last_price', None)}")
    except Exception as exc:  # noqa: BLE001
        print(f"{symbol}: ERROR {exc!r}")
