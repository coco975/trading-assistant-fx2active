from dataclasses import dataclass


@dataclass(frozen=True)
class BullishFibLevels:
    swing_low: float
    swing_high: float
    entry_78_6: float
    stop_loss: float
    take_profit: float

    @property
    def risk(self) -> float:
        return self.entry_78_6 - self.stop_loss

    @property
    def reward(self) -> float:
        return self.take_profit - self.entry_78_6

    @property
    def reward_to_risk(self) -> float:
        return self.reward / self.risk


def bullish_fib_levels(
    *,
    swing_low: float,
    swing_high: float,
    pip_size: float,
    retracement: float = 0.786,
    stop_buffer_pips: float = 10.0,
) -> BullishFibLevels:
    """Calculate bullish Fib levels using 100% at the swing low and 0% at the swing high."""
    if swing_high <= swing_low:
        raise ValueError("For a bullish impulse, swing_high must be above swing_low.")
    if not 0 < retracement < 1:
        raise ValueError("retracement must be between 0 and 1.")
    if pip_size <= 0:
        raise ValueError("pip_size must be positive.")
    if stop_buffer_pips <= 0:
        raise ValueError("stop_buffer_pips must be positive.")

    price_range = swing_high - swing_low
    entry = swing_high - retracement * price_range
    stop = swing_low - stop_buffer_pips * pip_size

    return BullishFibLevels(
        swing_low=swing_low,
        swing_high=swing_high,
        entry_78_6=entry,
        stop_loss=stop,
        take_profit=swing_high,
    )
