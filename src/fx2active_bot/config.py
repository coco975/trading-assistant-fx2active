from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    timeframe: str = "M15"
    fib_retracement: float = 0.786
    stop_buffer_pips: float = 10.0
    pip_size: float = 0.0001
    swing_left_bars: int = 2
    swing_right_bars: int = 2

    def __post_init__(self) -> None:
        if self.timeframe != "M15":
            raise ValueError("Strategy v0.1 is locked to M15.")
        if not 0 < self.fib_retracement < 1:
            raise ValueError("fib_retracement must be between 0 and 1.")
        if self.stop_buffer_pips <= 0:
            raise ValueError("stop_buffer_pips must be positive.")
        if self.pip_size <= 0:
            raise ValueError("pip_size must be positive.")
        if self.swing_left_bars < 1 or self.swing_right_bars < 1:
            raise ValueError("Swing lookback values must be >= 1.")
