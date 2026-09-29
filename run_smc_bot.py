from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.asset_config import get_active_asset
from src.market_data import get_price_data
from src.notifier import send_telegram
from src.smc_signal import SmcSignalResult, SmcZone, build_smc_signal

STATE_PATH = Path("data/smc_signal_state.csv")
STATE_COLUMNS = ["symbol", "last_checked_epoch", "last_bias", "last_zone_key"]


@dataclass
class BotState:
    last_checked_epoch: float
    last_bias: str    # "" means no bias last run
    last_zone_key: str  # "" means no zone last run


def _zone_key(zone: SmcZone | None) -> str:
    if zone is None:
        return ""
    return f"{zone.direction}:{zone.ob_low:.2f}-{zone.ob_high:.2f}"


def _load_state(symbol: str) -> BotState | None:
    if not STATE_PATH.exists():
        return None
    df = pd.read_csv(STATE_PATH, dtype=str, keep_default_na=False)
    match = df[df["symbol"] == symbol]
    if match.empty:
        return None
    row = match.iloc[-1]
    return BotState(
        last_checked_epoch=float(row["last_checked_epoch"]),
        last_bias=row.get("last_bias") or "",
        last_zone_key=row.get("last_zone_key") or "",
    )


def _save_state(symbol: str, epoch: float, bias: str, zone_key: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STATE_PATH.exists():
        df = pd.read_csv(STATE_PATH, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=STATE_COLUMNS)
    df = df[df["symbol"] != symbol]
    new_row = pd.DataFrame([{
        "symbol": symbol, "last_checked_epoch": str(epoch), "last_bias": bias, "last_zone_key": zone_key,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(STATE_PATH, index=False)


def _build_watch_message(symbol: str, result: SmcSignalResult) -> str:
    lines = [f"WATCH — {symbol}", f"H1 bias: {result.bias or 'unknown'}"]
    if result.zone:
        lines.append(f"M15 zone: {result.zone.direction} {result.zone.ob_low:.2f}-{result.zone.ob_high:.2f}")
        lines.append(
            "Waiting for: price to retest this zone, with an inducement sweep "
            "and a real target, to confirm a SETUP."
        )
    else:
        lines.append("M15 zone: none currently agrees with H1 bias -- nothing to watch yet.")
    return "\n".join(lines)


def main() -> None:
    asset = get_active_asset()

    print(f"Fetching {asset.display_name} H1 / M15 / M1 data...")
    bias_df = get_price_data(asset.data_symbol, period="1mo", interval="1h")
    zone_df = get_price_data(asset.data_symbol, period="60d", interval="15m")
    trigger_df = get_price_data(asset.data_symbol, period="7d", interval="1m")

    if bias_df.empty or zone_df.empty or trigger_df.empty:
        print("Missing data on one or more timeframes, aborting run.")
        return

    state = _load_state(asset.data_symbol)
    since = state.last_checked_epoch if state else None
    result = build_smc_signal(asset.display_name, bias_df, zone_df, trigger_df, since)

    print(f"H1 bias: {result.bias or 'unknown'}")
    if result.zone:
        print(f"M15 zone: {result.zone.direction} order block {result.zone.ob_low:.2f}-{result.zone.ob_high:.2f}")
    else:
        print("M15 zone: none")

    new_bias = result.bias or ""
    new_zone_key = _zone_key(result.zone)

    # Advance the watermark to the latest fetched M1 candle regardless of
    # outcome -- every candle up to here has now been scanned at least once,
    # signal or not, so there's nothing left to re-check next run.
    _save_state(asset.data_symbol, trigger_df.index[-1].timestamp(), new_bias, new_zone_key)

    if result.message:
        print("\n--- SIGNAL ---")
        print(result.message)
        print("--------------\n")
        send_telegram(result.message)
        return

    print(f"No SMC setup this run ({result.note}).")

    # Nothing fired, but tell the user what's forming if it's new since last
    # run -- so they're ready, without a Telegram message every 15 minutes
    # when nothing has actually changed.
    changed = state is None or state.last_bias != new_bias or state.last_zone_key != new_zone_key
    if changed:
        watch_message = _build_watch_message(asset.display_name, result)
        print("\n--- WATCH UPDATE ---")
        print(watch_message)
        print("--------------------\n")
        send_telegram(watch_message)
    else:
        print("No change in bias/zone since last run -- staying quiet.")


if __name__ == "__main__":
    main()
