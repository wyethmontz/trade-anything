from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.prop_firm_rules import PropFirmPhase

CHALLENGE_STATE_PATH = Path("data/challenge_state.csv")


@dataclass
class ChallengeLimitResult:
    blocked: bool
    reason: str
    daily_loss_pct: float
    total_loss_pct: float


def get_or_set_day_start_balance(
    symbol: str,
    current_balance: float,
    today: str,
    state_path: Path = CHALLENGE_STATE_PATH,
) -> float:
    """Return `symbol`'s UTC day-start balance for `today`, snapshotting
    `current_balance` the first time this is called on a new day."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        df = pd.read_csv(state_path)
    else:
        df = pd.DataFrame(columns=["symbol", "date", "day_start_balance"])

    match = df[(df["symbol"] == symbol) & (df["date"] == today)]
    if not match.empty:
        return float(match.iloc[-1]["day_start_balance"])

    df = df[df["symbol"] != symbol]
    new_row = pd.DataFrame([{"symbol": symbol, "date": today, "day_start_balance": current_balance}])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(state_path, index=False)
    return current_balance


def evaluate_challenge_limits(
    phase: PropFirmPhase,
    starting_balance: float,
    current_balance: float,
    day_start_balance: float,
) -> ChallengeLimitResult:
    total_loss_usd = max(starting_balance - current_balance, 0.0)
    total_loss_pct = (total_loss_usd / starting_balance * 100) if starting_balance > 0 else 0.0

    daily_loss_usd = max(day_start_balance - current_balance, 0.0)
    daily_loss_pct = (daily_loss_usd / day_start_balance * 100) if day_start_balance > 0 else 0.0

    if total_loss_pct >= phase.max_loss_pct:
        return ChallengeLimitResult(
            blocked=True,
            reason=f"{phase.display_name} max loss breached: {total_loss_pct:.2f}% >= {phase.max_loss_pct:.0f}% limit.",
            daily_loss_pct=daily_loss_pct,
            total_loss_pct=total_loss_pct,
        )

    if daily_loss_pct >= phase.max_daily_loss_pct:
        return ChallengeLimitResult(
            blocked=True,
            reason=(
                f"{phase.display_name} max daily loss breached: "
                f"{daily_loss_pct:.2f}% >= {phase.max_daily_loss_pct:.0f}% limit."
            ),
            daily_loss_pct=daily_loss_pct,
            total_loss_pct=total_loss_pct,
        )

    return ChallengeLimitResult(
        blocked=False,
        reason="Within challenge loss limits.",
        daily_loss_pct=daily_loss_pct,
        total_loss_pct=total_loss_pct,
    )


def utc_today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
