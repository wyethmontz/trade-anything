from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropFirmPhase:
    key: str
    display_name: str
    max_loss_pct: float
    max_daily_loss_pct: float
    target_pct: float | None
    consistency_pct: float | None
    min_trades: int | None
    min_withdrawal_usd: float | None
    payout_cap_usd: float | None
    profit_share: str | None
    leverage: str
    bonus_pct: float | None
    refund: str | None
    max_active_accounts: int | None
    price_usd: float | None


ONE_STEP = PropFirmPhase(
    key="one_step",
    display_name="1 Step",
    max_loss_pct=10.0,
    max_daily_loss_pct=3.0,
    target_pct=10.0,
    consistency_pct=None,
    min_trades=1,
    min_withdrawal_usd=None,
    payout_cap_usd=None,
    profit_share=None,
    leverage="1:100",
    bonus_pct=None,
    refund=None,
    max_active_accounts=1,
    price_usd=249.0,
)

TWO_STEP = PropFirmPhase(
    key="two_step",
    display_name="2 Steps",
    max_loss_pct=10.0,
    max_daily_loss_pct=3.0,
    target_pct=5.0,
    consistency_pct=None,
    min_trades=1,
    min_withdrawal_usd=None,
    payout_cap_usd=None,
    profit_share=None,
    leverage="1:100",
    bonus_pct=10.0,
    refund=None,
    max_active_accounts=None,
    price_usd=None,
)

FUNDED = PropFirmPhase(
    key="funded",
    display_name="Funded",
    max_loss_pct=10.0,
    max_daily_loss_pct=3.0,
    target_pct=100.0,
    consistency_pct=50.0,
    min_trades=None,
    min_withdrawal_usd=250.0,
    payout_cap_usd=3000.0,
    profit_share="80/20",
    leverage="1:100",
    bonus_pct=20.0,
    refund="Refund from 3rd payout",
    max_active_accounts=None,
    price_usd=None,
)


_REGISTRY: dict[str, PropFirmPhase] = {
    ONE_STEP.key: ONE_STEP,
    TWO_STEP.key: TWO_STEP,
    FUNDED.key: FUNDED,
}


def get_phase(key: str) -> PropFirmPhase:
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown prop firm phase '{key}'. Available: {available}") from exc
