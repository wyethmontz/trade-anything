# Trading Assistant Notes

This file is the persistent running log for strategy decisions, setup rules, losses, and adjustments.

## Workflow Rule

- Add a new entry for every meaningful trading update.
- Save to local git and push to GitHub immediately after each update.
- Keep entries short, factual, and actionable.

## Current Preferences

- User trades Gold on XM.
- Prefer 1H confirmation and avoid mid-range entries.
- Notify only when setup quality is very high confidence.

## Entries

### 2026-08-19

- Initialized notes workflow in repo.
- Added multi-source analysis focus: DXY, US10Y yields, VIX, oil, silver, S&P 500, and news context.
- Enforced risk-first behavior for small account sizing and minimum lot constraints.
- [2026-08-20 00:00] Paper BUY session record: BUY trigger confirmed above 4493.5; entry zone 4492.8-4493.6; SL 4489.8; TP 4498.5/4502.0; invalidate on 1H close below 4491.8; status: no valid SELL setup logged.
- [2026-08-20 00:00] Continuation note: next session should resume with BUY-only bias until a fresh 1H confirmation or a clean invalidation. No paper SELL trade exists for this session.

### 2026-08-20

- Added safe grid playbook in SAFE_GRID_RULES.md: max 3 layers, 3.0-dollar spacing, 2.5% basket hard stop, and kill-switch rules.
- Session continuity lock: paper trade state remains BUY from the prior session; reopen only after checking 1H candle at 2026-08-20 10:00 UTC+3 or on a clean invalidation below 4489.8.

### 2026-08-21

- Built automated hourly signal bot (`run_bot.py`, `.github/workflows/signal.yml`, cron-job.org trigger, Telegram notify-only, never auto-executes).
- Switched gold data source from `GC=F` futures to `PAXG-USD`: GC=F was drifting ~50-60 dollars from XM's actual XAUUSD price (contract roll/session gaps); PAXG-USD tracks spot within ~9-12 dollars.
- Backtested the advisor rule (SMA20/50 trend + RSI band + 1.5/3.0 ATR stop/target) walk-forward, no lookahead, spread-cost-adjusted: net profit factor ~1.06, expectancy +0.037R/trade over ~1000 trades. Thin, unproven edge -- treat as informational only, not a mandate to trade.
- Added signal tracker (`src/signal_tracker.py`): every rule-fired BUY/SELL is logged and auto-resolved against real price data (win/loss), tagged actionable vs tracked-only, log persisted via git commit from the workflow.
- **Incident: account went from $64.18 to $0.00.** Cause: two manually placed trades (10oz and 1oz GOLD, BUY) placed directly on XM outside the bot -- roughly 500x the bot's largest-ever suggested size (~0.02oz). Combined -$66.51 loss wiped the account. The bot was on WAIT the entire time; guardrails only ever covered bot-suggested sizes and have no reach over manual order entry on XM.
- Lesson: guardrails (min lot, risk cap, confidence floor) are advisory for anything typed directly into XM's order ticket -- they cannot block a manual oversized trade. Discipline to only act on bot-sized suggestions has to be a user commitment, not something the code can enforce remotely.
- Status: account at $0.00, no open positions. Bot infrastructure (schedule, tracker, backtest) stays live and continues logging signals for whenever the account is funded again.

### 2026-09-02

- Added Brent Crude Oil as a supported asset (`src/asset_config.py`, key `brent_crude`): data via `BZ=F` (ICE Brent futures), broker symbol `BRENTCash` (matches XM), 1000 barrels/lot, macro drivers WTI/DXY/XLE/VIX/US10Y, OPEC/inventory-focused news keywords. Selectable from the app sidebar or via `ASSET_KEY=brent_crude` for the bot; no other code changes needed since the app/bot are already generic over `asset_config.list_assets()`.
- User has a live BRENTCash position on XM (screenshot: 1.560 lots, entry near $98.22, -$7.80 unrealized). The 2026-09-02 17:07 UTC bot-style signal for Brent shows WAIT (downgraded from advisor by guardrails) despite an 85%-confidence bullish read -- consistent with the guardrail behavior documented above (confidence floor / feasibility / adaptive checks can downgrade even a high-confidence advisor call to WAIT).
- Set the `ASSET_KEY` repo variable to `brent_crude`; the scheduled bot now trades Brent by default. First live run fired a BUY (entry $95.84, TP $95.99, SL $95.69, confidence 85%).
- **Known basis gap:** XM's BRENTCash quote runs ~$2-3 above `BZ=F` (e.g. bot saw $95.84-95.79 while XM showed ~$98.03-98.08 within the same ~15 min window). Checked candidate Yahoo tickers (`BZT=F` returns garbage/$0.25, `^SGICBRB` is a points-based index, not $/barrel) -- no better free real-time substitute exists. Unlike the GC=F/gold fix (PAXG-USD tracked spot within $9-12), this gap looks like a genuine dated-Brent/futures backwardation premium during the current US-Iran/Strait of Hormuz supply-shock conditions, not a data bug. Treat bot entry/SL/TP levels as directional, not exact -- expect XM's actual fill price to run a few dollars above what the bot reports while this condition persists.

### 2026-09-05

- Added prop-firm challenge guardrail (`src/prop_firm_rules.py`, `src/challenge_guardrail.py`): encodes 1 Step / 2 Steps / Funded phase rules and enforces max loss (10%) / max daily loss (3%) as a hard guardrail, forcing WAIT on breach. Gold's `prop_firm_phase_key` defaults to `two_step` -- currently attempting Phase 1 then Phase 2 of a 2-Step evaluation (target 5% each, no time limit, min 1 trade).
- Added key levels (`src/key_levels.py`): swing high/low, prior day/week high-low, and round-number levels, shown on the chart and appended to every signal message. Informational only, doesn't feed entry/SL/TP or any guardrail.
- **TODO once the 2-Step evaluation is passed and a live funded account is issued:** in `src/asset_config.py`, change `GOLD`'s `prop_firm_phase_key` from `"two_step"` to `"funded"`, and set `CHALLENGE_STARTING_BALANCE` (env var or `challenge_starting_balance` field) to the new funded account's actual starting balance. Funded phase rules: 10% max loss, 3% max daily loss, 100% target, 50% daily consistency rule, $3000 payout cap, 80/20 profit share, 20% bonus, refund from 3rd payout. Tell the assistant "I passed, switch to funded" (with the funded account's starting balance) to make this change.

### 2026-09-13

- Added Bitcoin as a supported asset (`src/asset_config.py`, key `bitcoin`): `BTC-USD` data, XM's `BTCUSD` broker symbol, macro drivers weighted toward DXY/Nasdaq/US10Y/VIX/Gold. Switched the live bot to trade it (`ASSET_KEY=bitcoin`).
- Removed the Key Levels block from Telegram/bot signal messages per request -- key levels stay computed and shown on the app's chart, but no longer appear in the bot's message text.
- The repo was switched from private to public to unblock GitHub Actions, which had exhausted its free-tier minutes quota and was failing every run (no runner ever allocated). Public repos get unlimited free GitHub-hosted Actions minutes. Note: `NOTES.md`'s trading history is now publicly visible as a result.
- Tried GitHub Actions' own native `schedule` trigger (`cron: '*/15 * * * *'`) as a replacement for cron-job.org calling `workflow_dispatch`. It never fired once in several hours of testing (confirmed via `event: "schedule"` filter on the run history) despite valid YAML and an active workflow, while cron-job.org's external calls kept working reliably. Reverted to `workflow_dispatch`-only; cron-job.org remains the scheduling mechanism.
- Fixed a real gap in `src/notifier.py`: `send_telegram()` only checked the HTTP status code (`raise_for_status()`), never the response body's `"ok"` field. Telegram's Bot API can return HTTP 200 with `{"ok": false, ...}` for delivery failures (chat not found, bot blocked, etc.), which was being silently logged as a successful send. Now checks `ok` and logs the actual response when it's false.

### 2026-09-28

- Added Smart Money Concepts structure detection (`src/smc_structure.py`, `tests/test_smc_structure.py`): fractal swing detection pruned to a clean zigzag, Break of Structure (BOS) / Change of Character (CHoCH) events walked forward against candle closes, the order block (last opposite-colored candle before the impulse leg) behind the latest break, and recent liquidity sweeps (a wick through a swing point that closes back on the other side).
- Wired into `app.py` alongside the existing Key Levels: a new "Smart Money Structure" metrics row (trend, last BOS/CHoCH + level, order block range, recent sweep) and matching chart overlays (last-event level line, order block shaded zone). Informational only, same treatment as Key Levels -- does not feed `advisor.py`'s entry/SL/TP, any guardrail, or `run_bot.py`'s Telegram message. That's a deliberate choice, not an oversight: gating the live signal or the Telegram message on this is a real strategy change to an automated bot, worth its own decision entry rather than bundling it into this one.
- Verified: full test suite (19 tests) passes; `app.py` compiles and was smoke-tested via a headless Streamlit run (clean startup, HTTP 200, no traceback in server log).
- Open follow-up: decide whether SMC structure should (a) gate `run_bot.py`'s BUY/SELL like the macro/news source-alignment check already does, and/or (b) appear in the Telegram message text (Key Levels were explicitly removed from that message on 2026-09-13 -- same question applies here).
- Switched the live bot's `ASSET_KEY` repo variable from `bitcoin` back to `gold` -- it had been trading bitcoin since 2026-09-13 while all recent manual attention (this session included) has been on gold via XM. Confirmed via `gh variable list` before switching.
- Set `ACCOUNT_BALANCE` repo variable to `36.14` (this account's actual current balance, read live from the MT5 terminal), overriding Gold's stale `default_account_balance` ($64.18, pre-dates the August account wipe). Used balance, not equity ($49.70, which includes $13.56 non-withdrawable credit), for the more conservative risk-sizing base. Update this variable directly (`gh variable set ACCOUNT_BALANCE`) whenever the real balance changes -- it's a repo variable specifically so it doesn't need a code change to stay current.

### 2026-09-29

- Added a second, independent automated bot: `run_smc_bot.py` (`src/smc_signal.py`, `src/smc_structure.py` extended with a public `analyze_structure()`/`find_order_block()` -- refactor only, `compute_smc_structure()`'s existing behavior/tests unchanged). Mirrors tonight's local MT5-connected watcher's top-down logic, adapted for periodic (every ~15 min via `.github/workflows/smc_signal.yml` + your own external cron, e.g. cron-job.org -- same pattern as `signal.yml`) rather than continuous polling:
  - H1 sets the BIAS, M15 supplies the ZONE (only if it agrees with H1), M1 is the TRIGGER.
  - A signal requires an INDUCEMENT (a liquidity sweep since the zone formed) and a REAL target (a prior swept level or an untested opposing swing point -- never an invented R-multiple; skipped if neither exists).
  - Only fires on a genuine BUY/SETUP or SELL/SETUP -- no WAIT spam, no per-candle BOS/CHoCH noise sent to Telegram.
  - Because this runs periodically, not continuously, it scans every M1 candle since the last run (persisted watermark in `data/smc_signal_state.csv`, committed back by the workflow like `data/signal_log.csv`/`data/challenge_state.csv`), not just the newest one -- otherwise a setup that fully formed and resolved between two 15-minute runs would be missed entirely.
  - Same data-source caveat as `run_bot.py`: Yahoo Finance (`PAXG-USD` for gold), not a live XM/MT5 feed -- expect the same ~$9-12 basis gap already documented for gold.
  - This is a separate bot from `run_bot.py` (different entry point, different workflow, different Telegram message shape) -- both currently post to the same Telegram chat. Not yet merged into a single bot or reconciled against each other's signals; that's a deliberate open question, not an oversight.
  - Added `tests/test_smc_signal.py` (6 tests, all passing alongside the existing 20).
