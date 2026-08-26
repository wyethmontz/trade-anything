from __future__ import annotations

import pandas as pd
import yfinance as yf


def get_price_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV data for any yfinance symbol and normalize the columns."""
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    columns = ["Open", "High", "Low", "Close", "Volume"]
    df = df[columns].dropna()
    return df
