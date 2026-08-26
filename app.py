from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.advisor import build_advice
from src.asset_config import DEFAULT_ASSET_KEY, get_asset, list_assets
from src.broker_guardrails import BrokerSpec, evaluate_trade_feasibility
from src.context_sources import get_asset_news, get_external_asset_news, get_macro_snapshot, score_news_sentiment
from src.indicators import add_indicators
from src.journal import append_trade, get_journal_stats, load_journal
from src.market_data import get_price_data


st.set_page_config(page_title="Trading Assistant", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --ink: #0e1a2b;
        --accent: #00b386;
        --accent-soft: #d9f7ef;
        --surface: #f7faf9;
        --line: #dfe8e5;
    }
    .stApp {
        background: radial-gradient(1400px circle at 0% 0%, #eefaf6 0%, #f8fbfc 40%, #ffffff 90%);
    }
    .block-container {padding-top: 1.2rem;}
    .panel {
        background: rgba(255,255,255,0.92);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 16px 30px rgba(14,26,43,0.06);
    }
    .signal-buy {color: #008a5e; font-weight: 700;}
    .signal-sell {color: #d23b3b; font-weight: 700;}
    .signal-wait {color: #8c6b00; font-weight: 700;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=120)
def load_price_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return get_price_data(symbol, period, interval)


@st.cache_data(ttl=180)
def load_macro_data(asset_key: str, period: str, interval: str) -> tuple[pd.DataFrame, float]:
    return get_macro_snapshot(get_asset(asset_key), period=period, interval=interval)


@st.cache_data(ttl=300)
def load_news(asset_key: str, limit: int) -> pd.DataFrame:
    return get_asset_news(get_asset(asset_key), limit=limit)


@st.cache_data(ttl=300)
def load_external_news(asset_key: str, limit_per_feed: int) -> pd.DataFrame:
    return get_external_asset_news(get_asset(asset_key), limit_per_feed=limit_per_feed)


with st.sidebar:
    st.subheader("Session Setup")
    all_assets = list_assets()
    asset_keys = [a.key for a in all_assets]
    default_index = asset_keys.index(DEFAULT_ASSET_KEY) if DEFAULT_ASSET_KEY in asset_keys else 0
    selected_asset_key = st.selectbox(
        "Asset",
        asset_keys,
        index=default_index,
        format_func=lambda key: get_asset(key).display_name,
    )
    asset = get_asset(selected_asset_key)

    mode = st.selectbox(
        "Trading Style",
        ["Scalp (1m)", "Intraday (15m)", "Swing (1h)", "Position (1d)"],
        index=1,
    )
    account_balance = st.number_input(
        "Account Balance (USD)", min_value=1.0, value=asset.default_account_balance, step=10.0
    )
    risk_pct = st.slider("Risk Per Trade (%)", min_value=0.1, max_value=3.0, value=0.5, step=0.1)
    confidence_floor = st.slider("Base Confidence Floor (%)", min_value=50, max_value=90, value=65, step=1)
    adaptive_mode = st.toggle("Adaptive Mode After Losses", value=True)
    news_items = st.slider("Headlines to Show", min_value=5, max_value=15, value=8, step=1)

    st.subheader("Broker Guardrails")
    xm_symbol = st.text_input(f"{asset.display_name} Broker Symbol", value=asset.broker_symbol)
    contract_size = st.number_input(
        f"Contract Size ({asset.unit_label} per 1.00 lot)", min_value=1.0, value=asset.contract_size_per_lot, step=1.0
    )
    min_lot = st.number_input("Minimum Lot", min_value=0.001, value=asset.min_lot, step=0.001, format="%.3f")
    lot_step = st.number_input("Lot Step", min_value=0.001, value=asset.lot_step, step=0.001, format="%.3f")
    max_lot = st.number_input("Maximum Lot", min_value=0.01, value=asset.max_lot, step=0.01)
    spread_usd = st.number_input("Estimated Spread (USD)", min_value=0.0, value=asset.spread_estimate, step=0.01)

st.title(f"{asset.display_name} Trading Assistant")
st.caption(f"Rule-based assistant for {asset.broker_symbol} ideas. Educational use only, not financial advice.")

mode_map = {
    "Scalp (1m)": ("1d", "1m"),
    "Intraday (15m)": ("5d", "15m"),
    "Swing (1h)": ("1mo", "1h"),
    "Position (1d)": ("6mo", "1d"),
}

period, interval = mode_map[mode]
macro_period = "5d" if mode in {"Scalp (1m)", "Intraday (15m)"} else "1mo"
macro_interval = "1h" if mode in {"Scalp (1m)", "Intraday (15m)"} else "1d"

raw_df = load_price_data(asset.data_symbol, period, interval)
if raw_df.empty:
    st.error("No market data returned. Try another mode or retry in a moment.")
    st.stop()

analysis_df = add_indicators(raw_df).dropna().copy()
if analysis_df.empty:
    st.error("Indicators are not ready yet. Increase lookback period.")
    st.stop()

advice = build_advice(analysis_df, account_balance=account_balance, risk_pct=risk_pct)
latest = analysis_df.iloc[-1]
macro_df, macro_bias = load_macro_data(asset.key, period=macro_period, interval=macro_interval)
yahoo_news = load_news(asset.key, news_items)
external_news = load_external_news(asset.key, limit_per_feed=4)
news_df = pd.concat([yahoo_news, external_news], ignore_index=True).drop_duplicates(subset=["Headline"])
news_df = news_df.head(news_items)
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

col1, col2, col3, col4 = st.columns(4)
col1.metric(f"{asset.display_name} Price", f"${latest['Close']:,.2f}")
col2.metric("RSI (14)", f"{latest['RSI14']:.1f}")
col3.metric("Trend", advice.trend)
col4.metric("Confidence", f"{advice.confidence}%")

bias_label = "Bullish Pressure" if macro_bias > 15 else "Bearish Pressure" if macro_bias < -15 else "Mixed Pressure"
st.metric(f"Macro Bias For {asset.display_name}", f"{macro_bias:+.1f}", bias_label)
news_label = "News Lean Bullish" if news_sentiment > 8 else "News Lean Bearish" if news_sentiment < -8 else "News Mixed"
st.metric(f"News Sentiment For {asset.display_name}", f"{news_sentiment:+.1f}", news_label)

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

left, right = st.columns([2.2, 1.0], gap="large")

with left:
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=analysis_df.index,
                open=analysis_df["Open"],
                high=analysis_df["High"],
                low=analysis_df["Low"],
                close=analysis_df["Close"],
                name=asset.display_name,
            ),
            go.Scatter(x=analysis_df.index, y=analysis_df["SMA20"], mode="lines", name="SMA 20"),
            go.Scatter(x=analysis_df.index, y=analysis_df["SMA50"], mode="lines", name="SMA 50"),
        ]
    )
    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=12, b=12),
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    signal_class = {
        "BUY": "signal-buy",
        "SELL": "signal-sell",
        "WAIT": "signal-wait",
    }.get(execution_signal, "signal-wait")

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f"### Signal: <span class='{signal_class}'>{execution_signal}</span>", unsafe_allow_html=True)
    if execution_signal != advice.action:
        st.warning("Signal downgraded to WAIT by adaptive guardrails (risk/confidence/source alignment).")
    st.write(advice.notes)
    st.write(f"Entry: ${advice.entry:,.2f}")
    st.write(f"Stop Loss: ${advice.stop_loss:,.2f}")
    st.write(f"Take Profit: ${advice.take_profit:,.2f}")
    st.write(f"Risk Amount: ${advice.risk_amount:,.2f}")
    st.write(f"Suggested Size: {advice.position_size_units:,.2f} {asset.unit_label}")
    st.markdown("</div>", unsafe_allow_html=True)

st.subheader("Broker Execution Feasibility")
fx1, fx2, fx3, fx4 = st.columns(4)
fx1.metric("Effective Risk %", f"{effective_risk_pct:.2f}%")
fx2.metric("Rounded Lot Size", f"{feasibility.rounded_lots:.3f}")
fx3.metric("Effective Risk ($)", f"${feasibility.effective_risk_usd:,.2f}")
fx4.metric("Effective Risk (%)", f"{feasibility.effective_risk_pct:.2f}%")

if feasibility.tradable:
    st.success(feasibility.reason)
else:
    st.error(feasibility.reason)

st.subheader("Latest Candles")
preview_df = analysis_df[["Open", "High", "Low", "Close", "SMA20", "SMA50", "RSI14", "ATR14"]].tail(20)
st.dataframe(preview_df.style.format("{:.2f}"), use_container_width=True)

context_left, context_right = st.columns([1.15, 1.0], gap="large")

with context_left:
    st.subheader("Cross-Asset Movement Drivers")
    st.caption(f"These assets often move {asset.display_name} through USD strength, yields, and risk appetite.")
    if macro_df.empty:
        st.info("Macro source data is temporarily unavailable.")
    else:
        show_df = macro_df[["Driver", "Symbol", "Last", "Change %", "Impact"]].copy()
        st.dataframe(
            show_df.style.format({"Last": "{:.2f}", "Change %": "{:+.2f}%"}),
            use_container_width=True,
        )

with context_right:
    st.subheader(f"{asset.display_name} Headlines")
    st.caption("Merged from Yahoo ticker news and external macro feeds.")
    if news_df.empty:
        st.info("No headlines returned right now.")
    else:
        for _, row in news_df.iterrows():
            st.markdown(f"- [{row['Headline']}]({row['Link']})")
            st.caption(f"{row['Publisher']} | {row['Published']}")

st.subheader("Event Risk Checklist")
st.write("Use these before taking signals, especially around London/NY overlap:")
st.markdown("- US CPI / PCE inflation prints")
st.markdown("- FOMC rate decisions and Fed Chair speeches")
st.markdown("- US NFP and unemployment")
for item in asset.event_checklist_extra:
    st.markdown(f"- {item}")

st.subheader("Adaptive Journal (Loss Review)")
js1, js2, js3, js4 = st.columns(4)
js1.metric("Closed Trades", f"{journal_stats.total_closed}")
js2.metric("Win Rate", f"{journal_stats.win_rate:.1f}%")
js3.metric("Loss Rate", f"{journal_stats.loss_rate:.1f}%")
js4.metric("Current Loss Streak", f"{journal_stats.loss_streak}")

st.write("Current adaptation suggestions:")
for suggestion in journal_stats.suggestions:
    st.markdown(f"- {suggestion}")

with st.form("trade_log_form"):
    st.write("Log each closed trade so the assistant can adapt after losses.")
    outcome = st.selectbox("Outcome", ["Win", "Loss", "Breakeven", "Open"], index=3)
    pnl_usd = st.number_input("PnL (USD)", value=0.0, step=1.0)
    note = st.text_input("Notes", value="")
    submitted = st.form_submit_button("Save Trade To Journal")
    if submitted:
        append_trade(
            {
                "symbol": xm_symbol,
                "mode": mode,
                "signal": execution_signal,
                "entry": advice.entry,
                "stop_loss": advice.stop_loss,
                "take_profit": advice.take_profit,
                "suggested_lots": feasibility.rounded_lots,
                "risk_pct": effective_risk_pct,
                "macro_bias": macro_bias,
                "news_sentiment": news_sentiment,
                "confidence": advice.confidence,
                "outcome": outcome,
                "pnl_usd": pnl_usd,
                "notes": note,
            }
        )
        st.success("Trade saved. Reloading stats with your latest result.")
        st.rerun()
