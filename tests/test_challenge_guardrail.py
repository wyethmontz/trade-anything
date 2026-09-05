from src.challenge_guardrail import evaluate_challenge_limits
from src.prop_firm_rules import FUNDED


def test_within_limits_is_not_blocked():
    result = evaluate_challenge_limits(
        phase=FUNDED, starting_balance=10_000.0, current_balance=9_800.0, day_start_balance=9_900.0
    )

    assert result.blocked is False
    assert result.total_loss_pct == 2.0
    assert round(result.daily_loss_pct, 2) == 1.01


def test_max_loss_breach_blocks():
    result = evaluate_challenge_limits(
        phase=FUNDED, starting_balance=10_000.0, current_balance=8_900.0, day_start_balance=9_000.0
    )

    assert result.blocked is True
    assert "max loss" in result.reason.lower()


def test_max_daily_loss_breach_blocks():
    result = evaluate_challenge_limits(
        phase=FUNDED, starting_balance=10_000.0, current_balance=9_650.0, day_start_balance=9_950.0
    )

    assert result.blocked is True
    assert "daily loss" in result.reason.lower()


def test_no_loss_is_not_blocked():
    result = evaluate_challenge_limits(
        phase=FUNDED, starting_balance=10_000.0, current_balance=10_500.0, day_start_balance=10_200.0
    )

    assert result.blocked is False
    assert result.total_loss_pct == 0.0
    assert result.daily_loss_pct == 0.0
