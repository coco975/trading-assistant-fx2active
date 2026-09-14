from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .config import StrategyConfig
from .models import Candle
from .poi import ConfigurablePOIRule
from .runtime_settings import RuntimeSettingsStore
from .strategy import LongFibStrategy, TradeSetup


class WebControlledLongFibStrategy:
    """Reload web settings on every evaluation so changes take effect immediately."""

    def __init__(self, settings_path: str | Path, *, pip_size: float) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.pip_size = pip_size

    def find_setup(
        self,
        candles: Sequence[Candle],
        *,
        current_open_positions: int = 0,
    ) -> TradeSetup | None:
        settings = self.store.load()
        if not settings.trading_enabled or not settings.fib_enabled:
            return None
        if current_open_positions >= settings.max_open_positions:
            return None

        config = StrategyConfig(
            timeframe=settings.timeframe,
            fib_retracement=settings.fib_retracement,
            stop_buffer_pips=settings.stop_buffer_pips,
            pip_size=self.pip_size,
        )
        poi_rule = ConfigurablePOIRule(settings.poi, pip_size=self.pip_size)
        setup = LongFibStrategy(config, poi_rule).find_setup(candles)
        if setup is None or not candles:
            return None

        last = candles[-1]
        touched = last.low <= setup.entry <= last.high
        if settings.entry_trigger == "touch":
            return setup if touched else None
        if settings.entry_trigger == "close_back_above":
            return setup if last.low <= setup.entry and last.close > setup.entry else None
        if settings.entry_trigger == "bullish_close":
            return setup if touched and last.close > last.open and last.close >= setup.entry else None
        return None
