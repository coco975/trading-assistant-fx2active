from dataclasses import dataclass
from typing import Sequence

from .config import StrategyConfig
from .fibonacci import bullish_fib_levels
from .models import Candle
from .poi import PointOfInterestRule
from .swings import latest_bullish_swing_pair


@dataclass(frozen=True)
class TradeSetup:
    side: str
    timeframe: str
    entry: float
    stop_loss: float
    take_profit: float
    swing_low: float
    swing_high: float
    reward_to_risk: float


class LongFibStrategy:
    def __init__(self, config: StrategyConfig, poi_rule: PointOfInterestRule) -> None:
        self.config = config
        self.poi_rule = poi_rule

    def find_setup(self, candles: Sequence[Candle]) -> TradeSetup | None:
        pair = latest_bullish_swing_pair(
            candles,
            left=self.config.swing_left_bars,
            right=self.config.swing_right_bars,
        )
        if pair is None:
            return None

        low_index, high_index = pair
        levels = bullish_fib_levels(
            swing_low=candles[low_index].low,
            swing_high=candles[high_index].high,
            pip_size=self.config.pip_size,
            retracement=self.config.fib_retracement,
            stop_buffer_pips=self.config.stop_buffer_pips,
        )

        if not self.poi_rule.confirms_long(candles, levels):
            return None

        return TradeSetup(
            side="BUY",
            timeframe=self.config.timeframe,
            entry=levels.entry_78_6,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            swing_low=levels.swing_low,
            swing_high=levels.swing_high,
            reward_to_risk=levels.reward_to_risk,
        )
