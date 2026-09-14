import pytest

from fx2active_bot.fibonacci import bearish_fib_levels, bullish_fib_levels


def test_bullish_78_6_levels() -> None:
    levels = bullish_fib_levels(
        swing_low=1.1000,
        swing_high=1.1200,
        pip_size=0.0001,
        retracement=0.786,
        stop_buffer_pips=10,
    )

    assert levels.entry_78_6 == pytest.approx(1.10428)
    assert levels.stop_loss == pytest.approx(1.0990)
    assert levels.take_profit == pytest.approx(1.1200)
    assert levels.reward_to_risk > 0


def test_bearish_78_6_levels() -> None:
    levels = bearish_fib_levels(
        swing_high=1.1200,
        swing_low=1.1000,
        pip_size=0.0001,
        retracement=0.786,
        stop_buffer_pips=10,
    )

    assert levels.entry_78_6 == pytest.approx(1.11572)
    assert levels.stop_loss == pytest.approx(1.1210)
    assert levels.take_profit == pytest.approx(1.1000)
    assert levels.reward_to_risk > 0


def test_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        bullish_fib_levels(
            swing_low=1.1200,
            swing_high=1.1000,
            pip_size=0.0001,
        )
