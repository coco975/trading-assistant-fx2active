import pytest

from fx2active_bot.position_sizing import calculate_position_size
from fx2active_bot.runtime_settings import RuntimeSettings


def test_risk_percent_sizing_uses_equity_and_stop_loss_value():
    settings = RuntimeSettings(sizing_mode="risk_percent", risk_percent=1.0)
    result = calculate_position_size(
        settings,
        account_equity=5000.0,
        loss_per_one_lot=250.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    assert result.risk_amount == pytest.approx(50.0)
    assert result.volume == pytest.approx(0.20)


def test_fixed_cash_sizing():
    settings = RuntimeSettings(sizing_mode="fixed_cash", fixed_cash_risk=25.0)
    result = calculate_position_size(
        settings,
        account_equity=5000.0,
        loss_per_one_lot=100.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    assert result.risk_amount == pytest.approx(25.0)
    assert result.volume == pytest.approx(0.25)


def test_fixed_lot_sizing_does_not_need_equity_calculation():
    settings = RuntimeSettings(sizing_mode="fixed_lot", fixed_lot=0.12)
    result = calculate_position_size(
        settings,
        account_equity=0.0,
        loss_per_one_lot=None,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    assert result.risk_amount is None
    assert result.volume == pytest.approx(0.12)


def test_risk_too_small_for_broker_minimum_is_rejected():
    settings = RuntimeSettings(sizing_mode="fixed_cash", fixed_cash_risk=1.0)
    with pytest.raises(ValueError):
        calculate_position_size(
            settings,
            account_equity=1000.0,
            loss_per_one_lot=1000.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
