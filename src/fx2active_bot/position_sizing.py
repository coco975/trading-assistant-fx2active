from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR

from .runtime_settings import RuntimeSettings


@dataclass(frozen=True)
class PositionSize:
    volume: float
    risk_amount: float | None
    mode: str


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("Broker volume step must be positive")
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    units = (d_value / d_step).to_integral_value(rounding=ROUND_FLOOR)
    return float(units * d_step)


def calculate_position_size(
    settings: RuntimeSettings,
    *,
    account_equity: float,
    loss_per_one_lot: float | None,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> PositionSize:
    """Calculate the planned MT5 volume from the web-controlled account settings.

    `loss_per_one_lot` is the absolute account-currency loss for a 1.0 lot trade
    from the planned entry to the stop loss. The MT5 worker obtains that value via
    `order_calc_profit`, so FX conversion and symbol contract details stay broker-aware.
    """
    if volume_min <= 0 or volume_max <= 0 or volume_step <= 0:
        raise ValueError("Broker returned invalid volume limits")
    if volume_max < volume_min:
        raise ValueError("Broker volume maximum is below its minimum")

    if settings.sizing_mode == "fixed_lot":
        requested = settings.fixed_lot
        volume = _floor_to_step(requested, volume_step)
        if volume < volume_min:
            raise ValueError(
                f"Fixed lot {requested:g} is below the broker minimum {volume_min:g}"
            )
        if volume > volume_max:
            raise ValueError(
                f"Fixed lot {requested:g} is above the broker maximum {volume_max:g}"
            )
        return PositionSize(volume=volume, risk_amount=None, mode=settings.sizing_mode)

    if loss_per_one_lot is None or loss_per_one_lot <= 0:
        raise ValueError("Could not calculate stop-loss risk for 1.0 lot")

    if settings.sizing_mode == "risk_percent":
        if account_equity <= 0:
            raise ValueError("Account equity must be positive for percentage risk sizing")
        risk_amount = account_equity * settings.risk_percent / 100.0
    elif settings.sizing_mode == "fixed_cash":
        risk_amount = settings.fixed_cash_risk
    else:
        raise ValueError(f"Unsupported sizing mode: {settings.sizing_mode}")

    raw_volume = risk_amount / loss_per_one_lot
    volume = _floor_to_step(raw_volume, volume_step)
    if volume < volume_min:
        raise ValueError(
            "The selected risk is too small for this trade at the broker's minimum lot size"
        )
    volume = min(volume, volume_max)
    volume = _floor_to_step(volume, volume_step)

    return PositionSize(
        volume=volume,
        risk_amount=risk_amount,
        mode=settings.sizing_mode,
    )
