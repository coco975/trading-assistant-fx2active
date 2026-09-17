from dataclasses import dataclass
from typing import Sequence

from .config import StrategyConfig
from .fibonacci import bearish_fib_levels, bullish_fib_levels
from .models import Candle
from .poi import PointOfInterestRule
from .swings import latest_bearish_swing_pair, latest_bullish_swing_pair


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
    swing_low_time: str | None = None
    swing_high_time: str | None = None


def _build_long(
    candles: Sequence[Candle],
    pair: tuple[int, int],
    config: StrategyConfig,
    poi_rule: PointOfInterestRule,
) -> TradeSetup | None:
    low_index, high_index = pair
    levels = bullish_fib_levels(
        swing_low=candles[low_index].low,
        swing_high=candles[high_index].high,
        pip_size=config.pip_size,
        retracement=config.fib_retracement,
        stop_buffer_pips=config.stop_buffer_pips,
    )
    if not poi_rule.confirms_long(candles, levels):
        return None
    return TradeSetup(
        side="BUY",
        timeframe=config.timeframe,
        entry=levels.entry_78_6,
        stop_loss=levels.stop_loss,
        take_profit=levels.take_profit,
        swing_low=levels.swing_low,
        swing_high=levels.swing_high,
        reward_to_risk=levels.reward_to_risk,
        swing_low_time=candles[low_index].timestamp.isoformat(),
        swing_high_time=candles[high_index].timestamp.isoformat(),
    )


def _build_short(
    candles: Sequence[Candle],
    pair: tuple[int, int],
    config: StrategyConfig,
    poi_rule: PointOfInterestRule,
) -> TradeSetup | None:
    high_index, low_index = pair
    levels = bearish_fib_levels(
        swing_high=candles[high_index].high,
        swing_low=candles[low_index].low,
        pip_size=config.pip_size,
        retracement=config.fib_retracement,
        stop_buffer_pips=config.stop_buffer_pips,
    )
    if not poi_rule.confirms_short(candles, levels):
        return None
    return TradeSetup(
        side="SELL",
        timeframe=config.timeframe,
        entry=levels.entry_78_6,
        stop_loss=levels.stop_loss,
        take_profit=levels.take_profit,
        swing_low=levels.swing_low,
        swing_high=levels.swing_high,
        reward_to_risk=levels.reward_to_risk,
        swing_low_time=candles[low_index].timestamp.isoformat(),
        swing_high_time=candles[high_index].timestamp.isoformat(),
    )


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
        return _build_long(candles, pair, self.config, self.poi_rule)


class ShortFibStrategy:
    def __init__(self, config: StrategyConfig, poi_rule: PointOfInterestRule) -> None:
        self.config = config
        self.poi_rule = poi_rule

    def find_setup(self, candles: Sequence[Candle]) -> TradeSetup | None:
        pair = latest_bearish_swing_pair(
            candles,
            left=self.config.swing_left_bars,
            right=self.config.swing_right_bars,
        )
        if pair is None:
            return None
        return _build_short(candles, pair, self.config, self.poi_rule)


class DualFibStrategy:
    """Evaluate the most recent completed M15 impulses in either direction."""

    def __init__(self, config: StrategyConfig, poi_rule: PointOfInterestRule) -> None:
        self.config = config
        self.poi_rule = poi_rule

    def find_setup(
        self,
        candles: Sequence[Candle],
        *,
        allow_buys: bool = True,
        allow_sells: bool = True,
    ) -> TradeSetup | None:
        candidates: list[tuple[int, str, tuple[int, int]]] = []
        if allow_buys:
            bullish = latest_bullish_swing_pair(
                candles,
                left=self.config.swing_left_bars,
                right=self.config.swing_right_bars,
            )
            if bullish is not None:
                candidates.append((bullish[1], "BUY", bullish))
        if allow_sells:
            bearish = latest_bearish_swing_pair(
                candles,
                left=self.config.swing_left_bars,
                right=self.config.swing_right_bars,
            )
            if bearish is not None:
                candidates.append((bearish[1], "SELL", bearish))
        if not candidates:
            return None

        # The newest directional structure gets first priority, but a POI
        # rejection on that side must not suppress a valid candidate on the
        # opposite side. Evaluate both candidates in recency order.
        for _, side, pair in sorted(candidates, key=lambda item: item[0], reverse=True):
            if side == "BUY":
                setup = _build_long(candles, pair, self.config, self.poi_rule)
            else:
                setup = _build_short(candles, pair, self.config, self.poi_rule)
            if setup is not None:
                return setup
        return None
