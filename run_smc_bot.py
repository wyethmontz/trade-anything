from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.asset_config import get_active_asset
from src.market_data import get_price_data
from src.notifier import send_telegram
from src.smc_signal import build_smc_signal

STATE_PATH = Path("data/smc_signal_state.csv")


def _load_since(symbol: str) -> float | None:
    if not STATE_PATH.exists():
        return None
    df = pd.read_csv(STATE_PATH)
    match = df[df["symbol"] == symbol]
    if match.empty:
        return None
    return float(match.iloc[-1]["last_checked_epoch"])


def _save_since(symbol: str, epoch: float) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(STATE_PATH) if STATE_PATH.exists() else pd.DataFrame(columns=["symbol", "last_checked_epoch"])
    df = df[df["symbol"] != symbol]
    df = pd.concat([df, pd.DataFrame([{"symbol": symbol, "last_checked_epoch": epoch}])], ignore_index=True)
    df.to_csv(STATE_PATH, index=False)


def main() -> None:
    asset = get_active_asset()

    print(f"Fetching {asset.display_name} H1 / M15 / M1 data...")
    bias_df = get_price_data(asset.data_symbol, period="1mo", interval="1h")
    zone_df = get_price_data(asset.data_symbol, period="60d", interval="15m")
    trigger_df = get_price_data(asset.data_symbol, period="7d", interval="1m")

    if bias_df.empty or zone_df.empty or trigger_df.empty:
        print("Missing data on one or more timeframes, aborting run.")
        return

    since = _load_since(asset.data_symbol)
    result = build_smc_signal(asset.display_name, bias_df, zone_df, trigger_df, since)

    print(f"H1 bias: {result.bias or 'unknown'}")
    if result.zone:
        print(f"M15 zone: {result.zone.direction} order block {result.zone.ob_low:.2f}-{result.zone.ob_high:.2f}")
    else:
        print("M15 zone: none")

    # Advance the watermark to the latest fetched M1 candle regardless of
    # outcome -- every candle up to here has now been scanned at least once,
    # signal or not, so there's nothing left to re-check next run.
    _save_since(asset.data_symbol, trigger_df.index[-1].timestamp())

    if result.message:
        print("\n--- SIGNAL ---")
        print(result.message)
        print("--------------\n")
        send_telegram(result.message)
    else:
        print(f"No SMC setup this run ({result.note}).")


if __name__ == "__main__":
    main()
