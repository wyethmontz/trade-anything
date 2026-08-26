from __future__ import annotations

import os
from datetime import datetime, timezone

from src.advisor import build_advice
from src.asset_config import AssetConfig, get_active_asset
from src.broker_guardrails import BrokerSpec, evaluate_trade_feasibility
from src.context_sources import get_asset_news, get_external_asset_news, get_macro_snapshot, score_news_sentiment
from src.indicators import add_indicators
from src.journal import get_journal_stats, load_journal
from src.market_data import get_price_data
from src.notifier import send_telegram
from src.signal_tracker import has_open_signal, log_signal, resolve_open_signals
from src.trading_mode import DEFAULT_TRADING_MODE, get_trading_mode


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    return float(value) if value else default


def build_message(
    now: datetime,
    asset: AssetConfig,
    execution_signal: str,
    downgraded: bool,
    advice,
    feasibility,
    effective_risk_pct: float,
) -> str:
    signal_line = f"<b>Signal: {execution_signal}</b>"
    if downgraded:
        signal_line += " (downgraded from advisor by guardrails)"

    if execution_signal == "WAIT":
        return (
            f"<b>{asset.display_name} Signal — {now.strftime('%Y-%m-%d %H:%M UTC')}</b>\n\n"
            f"{signal_line}\n"
            f"Trend: {advice.trend} | Confidence: {advice.confidence}%"
        )

    price_label = f"{execution_signal.capitalize()} When Price is"
    display_entry = advice.entry + asset.spread_estimate if execution_signal == "BUY" else advice.entry
    stop_distance = abs(advice.entry - advice.stop_loss)
    target_distance = abs(advice.take_profit - advice.entry)

    return (
        f"<b>{asset.display_name} Signal — {now.strftime('%Y-%m-%d %H:%M UTC')}</b>\n\n"
        f"{signal_line}\n"
        f"Trend: {advice.trend} | Confidence: {advice.confidence}%\n\n"
        f"Lot(s): {feasibility.rounded_lots:.3f}\n"
        f"{price_label}: ${display_entry:,.2f}\n"
        f"Take Profit Level: ${advice.take_profit:,.2f}\n"
        f"Stop Loss Level: ${advice.stop_loss:,.2f}\n"
        f"Entry - SL: ${stop_distance:,.2f}\n"
        f"TP - Entry: ${target_distance:,.2f}\n\n"
        f"Risk: ${advice.risk_amount:,.2f} ({effective_risk_pct:.2f}%)\n"
        f"Suggested Size: {advice.position_size_units:,.2f} {asset.unit_label}"
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    asset = get_active_asset()

    account_balance = _env_float("ACCOUNT_BALANCE", asset.default_account_balance)
    risk_pct = _env_float("RISK_PCT", 0.5)
    confidence_floor = _env_float("CONFIDENCE_FLOOR", 65)
    adaptive_mode = os.environ.get("ADAPTIVE_MODE", "true").lower() != "false"

    xm_symbol = os.environ.get("XM_SYMBOL", asset.broker_symbol)
    contract_size = _env_float("CONTRACT_SIZE", asset.contract_size_per_lot)
    min_lot = _env_float("MIN_LOT", asset.min_lot)
    lot_step = _env_float("LOT_STEP", asset.lot_step)
    max_lot = _env_float("MAX_LOT", asset.max_lot)
    spread_usd = _env_float("SPREAD_USD", asset.spread_estimate)

    trading_mode_key = os.environ.get("TRADING_MODE", DEFAULT_TRADING_MODE)
    trading_mode = get_trading_mode(trading_mode_key)

    print(f"Fetching {asset.display_name} data ({trading_mode_key}, {trading_mode['interval']})...")
    raw_df = get_price_data(asset.data_symbol, period=trading_mode["period"], interval=trading_mode["interval"])
    if raw_df.empty:
        print("No market data returned, aborting run.")
        return

    analysis_df = add_indicators(raw_df).dropna().copy()
    if analysis_df.empty:
        print("Indicators not ready yet (insufficient lookback), aborting run.")
        return

    advice = build_advice(analysis_df, account_balance=account_balance, risk_pct=risk_pct)

    print("Fetching macro snapshot and news...")
    macro_df, macro_bias = get_macro_snapshot(asset, period="1mo", interval="1d")
    yahoo_news = get_asset_news(asset, limit=8)
    external_news = get_external_asset_news(asset, limit_per_feed=4)
    news_df = yahoo_news
    if not external_news.empty:
        import pandas as pd

        news_df = pd.concat([yahoo_news, external_news], ignore_index=True).drop_duplicates(subset=["Headline"])
    news_sentiment = score_news_sentiment(news_df, asset)

    journal_df = load_journal()
    journal_stats = get_journal_stats(journal_df)

    effective_risk_pct = risk_pct
    effective_confidence_floor = confidence_floor
    if adaptive_mode:
        effective_risk_pct = min(risk_pct, journal_stats.recommended_risk_cap)
        effective_confidence_floor = max(confidence_floor, journal_stats.recommended_confidence_floor)

    spec = BrokerSpec(
        symbol=xm_symbol,
        contract_size_per_lot=contract_size,
        min_lot=min_lot,
        lot_step=lot_step,
        max_lot=max_lot,
        spread_usd=spread_usd,
    )
    feasibility = evaluate_trade_feasibility(
        account_balance=account_balance,
        risk_pct=effective_risk_pct,
        entry=advice.entry,
        stop=advice.stop_loss,
        spec=spec,
    )

    source_alignment = True
    if advice.action == "BUY":
        source_alignment = macro_bias >= 0 and news_sentiment >= -10
    elif advice.action == "SELL":
        source_alignment = macro_bias <= 0 and news_sentiment <= 10

    execution_signal = advice.action
    if advice.action != "WAIT":
        if advice.confidence < effective_confidence_floor:
            execution_signal = "WAIT"
        if not feasibility.tradable:
            execution_signal = "WAIT"
        if adaptive_mode and journal_stats.loss_streak >= 2 and not source_alignment:
            execution_signal = "WAIT"

    downgraded = execution_signal != advice.action

    print("Resolving open tracked signals against fresh price data...")
    resolve_open_signals(
        symbol=asset.data_symbol,
        period=trading_mode["resolve_period"],
        interval=trading_mode["resolve_interval"],
    )

    # When polled frequently (e.g. every couple of minutes for scalping), the same
    # trend can keep firing the same BUY/SELL on every run. Skip logging/notifying
    # again while that signal is still open — a fresh notification only makes sense
    # once it resolves (win/loss) and a new setup fires.
    is_duplicate = False
    if advice.action in ("BUY", "SELL"):
        is_duplicate = has_open_signal(asset.data_symbol, advice.action)
        if is_duplicate:
            print(f"[run_bot] {advice.action} on {asset.data_symbol} is already open and unresolved; skipping duplicate log/notify.")
        else:
            log_signal(
                now=now,
                symbol=asset.data_symbol,
                action=advice.action,
                entry=advice.entry,
                stop=advice.stop_loss,
                target=advice.take_profit,
                confidence=advice.confidence,
                trend=advice.trend,
                actionable=(execution_signal == advice.action),
            )

    message = build_message(
        now=now,
        asset=asset,
        execution_signal=execution_signal,
        downgraded=downgraded,
        advice=advice,
        feasibility=feasibility,
        effective_risk_pct=effective_risk_pct,
    )

    print("\n--- MESSAGE PREVIEW ---")
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="replace").decode("ascii"))
    print("-----------------------\n")

    if is_duplicate:
        print("[run_bot] Skipping Telegram send: duplicate of an already-open signal.")
        return

    include_wait = os.environ.get("INCLUDE_WAIT_SIGNALS", "true").lower() == "true"
    only_send_buy = os.environ.get("ONLY_SEND_BUY", "true").lower() == "true"

    if only_send_buy and execution_signal != "BUY":
        print(f"[run_bot] ONLY_SEND_BUY is enabled and signal is {execution_signal}, skipping Telegram send.")
    elif execution_signal == "WAIT" and not include_wait:
        print("[run_bot] Signal is WAIT, skipping Telegram send.")
    else:
        send_telegram(message)


if __name__ == "__main__":
    main()
