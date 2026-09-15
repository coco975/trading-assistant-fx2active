from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .config import StrategyConfig
from .models import Candle
from .poi import ConfigurablePOIRule
from .runtime_settings import RuntimeSettingsStore
from .strategy import DualFibStrategy, TradeSetup


class WebControlledFibStrategy:
    """Reload web settings on every evaluation so changes take effect immediately."""

    def __init__(self, settings_path: str | Path, *, pip_size: float) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.pip_size = pip_size

    def find_setup(
        self,
        candles: Sequence[Candle],
        *,
        current_open_positions: int = 0,
        current_bar_is_open: bool = False,
    ) -> TradeSetup | None:
        settings = self.store.load()
        if not settings.trading_enabled or not settings.fib_enabled:
            return None
        if current_open_positions >= settings.max_open_positions:
            return None
        if not settings.allow_buys and not settings.allow_sells:
            return None
        if not candles:
            return None

        # MT5 position-0 rates include the currently forming M15 candle. Never
        # use that unfinished candle to confirm fractal structure or a close.
        if current_bar_is_open:
            if len(candles) < 2:
                return None
            structure_candles: Sequence[Candle] = candles[:-1]
        else:
            structure_candles = candles

        if not structure_candles:
            return None

        config = StrategyConfig(
            timeframe=settings.timeframe,
            fib_retracement=settings.fib_retracement,
            stop_buffer_pips=settings.stop_buffer_pips,
            pip_size=self.pip_size,
        )
        poi_rule = ConfigurablePOIRule(settings.poi, pip_size=self.pip_size)
        setup = DualFibStrategy(config, poi_rule).find_setup(
            structure_candles,
            allow_buys=settings.allow_buys,
            allow_sells=settings.allow_sells,
        )
        if setup is None:
            return None

        # Pending limits are intentionally placed at the Fib price before a
        # market touch. Their structure/POI qualification still uses closed bars.
        if settings.execution_mode == "pending_limit":
            return setup

        if settings.entry_trigger == "touch":
            trigger = candles[-1]
            touched = trigger.low <= setup.entry <= trigger.high
            return setup if touched else None

        # Close-based triggers use the most recent completed M15 candle.
        trigger = structure_candles[-1]
        touched = trigger.low <= setup.entry <= trigger.high

        if settings.entry_trigger == "close_back_in_direction":
            if setup.side == "BUY":
                confirmed = trigger.low <= setup.entry and trigger.close > setup.entry
            else:
                confirmed = trigger.high >= setup.entry and trigger.close < setup.entry
            return setup if confirmed else None

        if settings.entry_trigger == "directional_close":
            if setup.side == "BUY":
                confirmed = touched and trigger.close > trigger.open and trigger.close >= setup.entry
            else:
                confirmed = touched and trigger.close < trigger.open and trigger.close <= setup.entry
            return setup if confirmed else None

        return None


# Backward-compatible alias for code created before sell support was added.
WebControlledLongFibStrategy = WebControlledFibStrategy
