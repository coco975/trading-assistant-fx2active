from dataclasses import dataclass
from pathlib import Path

from .config import StrategyConfig
from .runtime_settings import RuntimeSettings, RuntimeSettingsStore


@dataclass(frozen=True)
class WorkerDecision:
    allowed: bool
    reason: str


class WorkerControl:
    """Bridge between the web control settings and the trading worker."""

    def __init__(self, settings_path: str | Path, *, pip_size: float) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.pip_size = pip_size

    def current_settings(self) -> RuntimeSettings:
        return self.store.load()

    def strategy_config(self) -> StrategyConfig:
        settings = self.current_settings()
        return StrategyConfig(
            timeframe=settings.timeframe,
            fib_retracement=settings.fib_retracement,
            stop_buffer_pips=settings.stop_buffer_pips,
            pip_size=self.pip_size,
        )

    def can_open_position(self, current_open_positions: int) -> WorkerDecision:
        settings = self.current_settings()
        if not settings.trading_enabled:
            return WorkerDecision(False, "Trading is disabled from the web panel")
        if not settings.fib_enabled:
            return WorkerDecision(False, "The Fibonacci entry rule is disabled")
        if current_open_positions >= settings.max_open_positions:
            return WorkerDecision(False, "Maximum open positions reached")
        return WorkerDecision(True, "Entry may be evaluated")
