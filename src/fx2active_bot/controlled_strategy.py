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
    ) -> TradeSetup | None:
        settings = self.store.load()
        if not settings.trading_enabled or not settings.fib_enabled:
            return None
        if current_open_positions >= settings.max_open_positions:
            return None
        if not settings.allow_buys and not settings.allow_sells:
            return None

        config = StrategyConfig(
            timeframe=settings.timeframe,
            fib_retracement=settings.fib_retracement,
            stop_buffer_pips=settings.stop_buffer_pips,
            pip_size=self.pip_size,
        )
        poi_rule = ConfigurablePOIRule(settings.poi, pip_size=self.pip_size)
        setup = DualFibStrategy(config, poi_rule).find_setup(
            candles,
            allow_buys=settings.allow_buys,
            allow_sells=settings.allow_sells,
        )
        if setup is None or not candles:
            return None

        # A pending limit is intentionally placed at the Fib price before a market
        # touch. Market mode still waits for the selected confirmation trigger.
        if settings.execution_mode == "pending_limit":
            return setup

        last = candles[-1]
        touched = last.low <= setup.entry <= last.high
        if settings.entry_trigger == "touch":
            return setup if touched else None

        if settings.entry_trigger == "close_back_in_direction":
            if setup.side == "BUY":
                confirmed = last.low <= setup.entry and last.close > setup.entry
            else:
                confirmed = last.high >= setup.entry and last.close < setup.entry
            return setup if confirmed else None

        if settings.entry_trigger == "directional_close":
            if setup.side == "BUY":
                confirmed = touched and last.close > last.open and last.close >= setup.entry
            else:
                confirmed = touched and last.close < last.open and last.close <= setup.entry
            return setup if confirmed else None

        return None


# Backward-compatible alias for code created before sell support was added.
WebControlledLongFibStrategy = WebControlledFibStrategy
