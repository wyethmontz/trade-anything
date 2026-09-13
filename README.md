# Trading Assistant

A lightweight, multi-asset trading assistant. Which market it trades is a config choice
(`src/asset_config.py`), not a hardcoded assumption — switch it from the app's sidebar,
or via the `ASSET_KEY` environment variable for the automated bot. Ships with **Gold**
(XAUUSD proxy via `PAXG-USD`), **Natural Gas** (`NG=F`, XM's `NGASCash`), **Brent
Crude Oil** (`BZ=F`, XM's `BRENTCash`), and **Bitcoin** (`BTC-USD`, XM's `BTCUSD`)
configured; add another asset by adding one `AssetConfig` entry.

Features:

- Real-time OHLC data pull from Yahoo Finance
- Candlestick chart with SMA20 and SMA50 overlays
- Key levels: last confirmed swing high/low plus prior day and prior week high/low, shown on the app's chart
- RSI and ATR-based setup detection
- Rule-based BUY / SELL / WAIT signal
- Simple risk and position size estimation
- Cross-asset macro dashboard (drivers are per-asset, e.g. DXY/US10Y/VIX/Oil/Silver for gold)
- Weighted macro bias score to estimate directional pressure on the active asset
- Live ticker-linked headline feed for the active asset
- Event risk checklist for high-impact macro sessions (plus asset-specific items)
- External macro news feeds (Reuters/MarketWatch/FXStreet RSS)
- Broker guardrails (lot step, min lot, spread-aware risk feasibility)
- Adaptive loss review journal that tightens risk/confidence after drawdowns

## Switching Assets

- **In the app**: pick from the "Asset" dropdown at the top of the sidebar.
- **For the automated bot**: set the `ASSET_KEY` environment variable (`gold`,
  `natural_gas`, `brent_crude`, or `bitcoin`) before running `run_bot.py`, or as a
  repo variable/secret for the GitHub Actions workflow. Defaults to `natural_gas`.
- **To add a new asset**: add an `AssetConfig` entry in `src/asset_config.py` with its
  data symbol, broker symbol, contract spec, macro drivers, and news keywords.

Signals logged to `data/signal_log.csv` are tagged with the symbol they were traded
against, so switching assets doesn't mix up win/loss tracking between them.

## Broker Setup Notes

Before using live funds, set these exactly from your broker's symbol specification:

- Contract size (units per 1.00 lot)
- Minimum lot
- Lot step
- Maximum lot
- Typical spread

The app will downgrade a trade to `WAIT` when:

- The position is not feasible at your risk cap
- Confidence is below the active floor
- Adaptive mode detects a losing streak and source misalignment
- A configured prop-firm challenge phase's max loss or max daily loss limit is breached (see below)

## Key Levels

`src/key_levels.py` computes, from whatever OHLC history the active trading mode fetched:

- **Swing High / Low**: the most recent confirmed pivot — a bar whose high (or low) is the
  extreme within 5 bars on both sides. The trailing 5 bars are excluded since they can't yet
  be confirmed as a pivot.
- **Prior Day / Week High-Low**: the high and low of the most recently *completed* calendar
  day/week, excluding the still-in-progress current one.
- **Round Numbers**: the nearest psychological round-number levels above and below the current
  price, at a spacing scaled to the instrument's price magnitude (e.g. $100 steps for ~$4400
  gold, $1 steps for ~$95 oil, $0.10 steps for ~$2.50 natural gas).

These are informational (shown on the app's chart only — Telegram/bot signal messages don't
include them) and don't feed into the advisor's entry/SL/TP or any guardrail. A level shows as
unavailable when there isn't enough history in the current trading mode's lookback window to
confirm it (e.g. Scalp mode's 5-day window may not contain a fully completed prior week).

## Prop Firm Challenge Guardrail

When an asset has a `prop_firm_phase_key` set (Gold defaults to `funded`, see `src/prop_firm_rules.py` for the
`one_step` / `two_step` / `funded` phase definitions), the bot tracks your account balance against that phase's
max loss and max daily loss limits and forces `WAIT` once either is breached — the same hard-guardrail treatment
as broker feasibility. Max loss is measured against `CHALLENGE_STARTING_BALANCE` (your funded account's initial
size); max daily loss is measured against a UTC day-start balance snapshotted automatically in
`data/challenge_state.csv` the first time the bot runs each day. This only tracks loss limits (the two rules that
actually gate whether a trade should fire) — target/consistency/payout/profit-share terms are account terms, not
per-signal guardrails, so they aren't enforced here.

## Journal Workflow

After each trade closes:

1. Log outcome (Win/Loss/Breakeven)
2. Log actual PnL
3. Add a short note

The app analyzes recent closed trades and automatically recommends tighter risk and higher confidence thresholds after losses.

## Quick Start

1. Create and activate a virtual environment:

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Run the app:

   ```powershell
   streamlit run app.py
   ```

## Notes

- The assistant is educational and not financial advice.
- Always confirm signals with your own analysis and broker constraints.

## Automated Signal Bot

`run_bot.py` runs the same advisor pipeline headless (Swing 1h data, macro/news guardrails, adaptive journal risk cap) and sends the resulting signal to Telegram. It only ever notifies — it never places trades.

### Run locally

```powershell
$env:TELEGRAM_BOT_TOKEN = "your_bot_token"
$env:TELEGRAM_CHAT_ID = "your_chat_id"
python run_bot.py
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | required to send |
| `TELEGRAM_CHAT_ID` | Target chat/channel id | required to send |
| `ASSET_KEY` | Which asset to trade (`gold`, `natural_gas`, `brent_crude`, `bitcoin`) | `natural_gas` |
| `TRADING_MODE` | Candle granularity: `scalp` (1m), `intraday` (15m), `swing` (1h), `position` (1d). Also controls how far back open signals are re-checked for a stop/target hit. | `scalp` |
| `ACCOUNT_BALANCE` | Account balance in USD | active asset's default |
| `RISK_PCT` | Risk per trade (%) | `0.5` |
| `CONFIDENCE_FLOOR` | Minimum confidence to act on a signal | `65` |
| `ADAPTIVE_MODE` | Tighten risk/confidence after a loss streak | `true` |
| `XM_SYMBOL`, `CONTRACT_SIZE`, `MIN_LOT`, `LOT_STEP`, `MAX_LOT`, `SPREAD_USD` | Broker guardrail specs | active asset's defaults in `src/asset_config.py` |
| `PROP_FIRM_PHASE` | Prop-firm challenge phase to enforce (`one_step`, `two_step`, `funded`) from `src/prop_firm_rules.py`, or unset to disable | active asset's `prop_firm_phase_key` (Gold defaults to `funded`) |
| `CHALLENGE_STARTING_BALANCE` | The funded/challenge account's initial size, used for the max-loss % check | active asset's `challenge_starting_balance`, else `ACCOUNT_BALANCE` |
| `ONLY_SEND_BUY` | Only send a Telegram message when the signal is `BUY` (skips `SELL` and `WAIT`). Set to `true` to only receive BUY alerts. | `false` |
| `INCLUDE_WAIT_SIGNALS` | When `ONLY_SEND_BUY` is `false`, whether to also send `WAIT` signals | `true` |

### Automated schedule

[.github/workflows/signal.yml](.github/workflows/signal.yml) runs on GitHub's own `schedule` trigger (currently every 15 minutes, cron `*/15 * * * *`) — no external cron service required. `workflow_dispatch` is also enabled for manual/API-triggered test runs. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repo secrets, and optionally `ASSET_KEY` / `TRADING_MODE` / `ACCOUNT_BALANCE` / `RISK_PCT` as repo variables, before enabling the schedule. Runs are queued (see `concurrency` in the workflow) so overlapping triggers can't race on the signal-log commit, and duplicate BUY/SELL signals from the same still-open setup are skipped automatically (`signal_tracker.has_open_signal`).

Note: GitHub's `schedule` trigger is best-effort — during periods of high GitHub Actions load, a run can fire a few minutes late (GitHub does not guarantee exact timing), and scheduled workflows are automatically disabled if the repo has no commits for 60 days (any push re-enables it).

**Polling frequency vs. GitHub Actions minutes**: on a public repo, GitHub-hosted Actions runners are free and unmetered. On a private repo, Actions bills against a monthly minutes quota (2,000 min/month on the free tier), with each run rounding up to at least 1 billed minute regardless of how fast it finishes — polling every 1-2 minutes means ~700+ runs/day, enough to exhaust a private repo's free quota in a few days. If you need true multi-minute scalping cadence on a private repo, run `run_bot.py` from somewhere with its own always-on scheduler (a local cron job, a small VPS, etc.) instead of GitHub Actions, and reserve the Actions workflow for a slower cadence that stays within the free quota.

### Run with Docker

```bash
docker build -t trading-signal-bot .
docker run -e TELEGRAM_BOT_TOKEN=your_bot_token -e TELEGRAM_CHAT_ID=your_chat_id -e ASSET_KEY=natural_gas trading-signal-bot
```
