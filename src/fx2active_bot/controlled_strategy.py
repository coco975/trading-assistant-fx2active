from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .config import StrategyConfig
from .models import Candle
from .poi import ConfigurablePOIRule
from .runtime_settings import RuntimeSettingsStore
from .strategy import DualFibStrategy, TradeSetup
from .swings import latest_bearish_swing_pair, latest_bullish_swing_pair


class WebControlledFibStrategy:
    """Reload web settings on every evaluation so changes take effect immediately."""

    def __init__(self, settings_path: str | Path, *, pip_size: float) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.pip_size = pip_size
        self.last_decision: dict[str, Any] = {
            "stage": "starting",
            "ready": False,
            "reason": "Strategy evaluation has not run yet.",
        }

    def _decision(self, stage: str, reason: str, *, ready: bool = False, **details: Any) -> None:
        self.last_decision = {
            "stage": stage,
            "ready": ready,
            "reason": reason,
            **details,
        }

    def find_setup(
        self,
        candles: Sequence[Candle],
        *,
        current_open_positions: int = 0,
        current_bar_is_open: bool = False,
    ) -> TradeSetup | None:
        settings = self.store.load()
        if not settings.trading_enabled:
            self._decision("controls", "Trading Active is OFF.")
            return None
        if not settings.fib_enabled:
            self._decision("controls", "Fibonacci Entry is OFF.")
            return None
        if current_open_positions >= settings.max_open_positions:
            self._decision(
                "position_limit",
                "Maximum Open Positions has been reached.",
                current_open_positions=current_open_positions,
                max_open_positions=settings.max_open_positions,
            )
            return None
        if not settings.allow_buys and not settings.allow_sells:
            self._decision("direction", "Both BUY and SELL are disabled.")
            return None
        if not candles:
            self._decision("market_data", "No M15 candles are available from MT5.")
            return None

        # MT5 position-0 rates include the currently forming M15 candle. Never
        # use that unfinished candle to confirm fractal structure or a close.
        if current_bar_is_open:
            if len(candles) < 2:
                self._decision("market_data", "Waiting for completed M15 candles.")
                return None
            structure_candles: Sequence[Candle] = candles[:-1]
        else:
            structure_candles = candles

        if not structure_candles:
            self._decision("market_data", "Waiting for completed M15 candles.")
            return None

        config = StrategyConfig(
            timeframe=settings.timeframe,
            fib_retracement=settings.fib_retracement,
            stop_buffer_pips=settings.stop_buffer_pips,
            pip_size=self.pip_size,
        )
        poi_rule = ConfigurablePOIRule(settings.poi, pip_size=self.pip_size)

        bullish_pair = (
            latest_bullish_swing_pair(
                structure_candles,
                left=config.swing_left_bars,
                right=config.swing_right_bars,
            )
            if settings.allow_buys
            else None
        )
        bearish_pair = (
            latest_bearish_swing_pair(
                structure_candles,
                left=config.swing_left_bars,
                right=config.swing_right_bars,
            )
            if settings.allow_sells
            else None
        )

        setup = DualFibStrategy(config, poi_rule).find_setup(
            structure_candles,
            allow_buys=settings.allow_buys,
            allow_sells=settings.allow_sells,
        )
        if setup is None:
            if bullish_pair is None and bearish_pair is None:
                self._decision(
                    "structure",
                    "No confirmed M15 swing impulse is available yet.",
                    bullish_structure=False,
                    bearish_structure=False,
                )
            else:
                evidence = poi_rule.last_evidence.as_dict() if poi_rule.last_evidence is not None else {}
                self._decision(
                    "poi",
                    "A Fib structure exists, but the enabled structural POI requirement is not met.",
                    bullish_structure=bullish_pair is not None,
                    bearish_structure=bearish_pair is not None,
                    poi_evidence=evidence,
                    min_confirmations=settings.poi.min_confirmations,
                )
            return None

        setup_details = {
            "side": setup.side,
            "entry": setup.entry,
            "swing_low": setup.swing_low,
            "swing_high": setup.swing_high,
        }

        # Pending limits are intentionally placed at the Fib price before a
        # market touch. Their structure/POI qualification still uses closed bars.
        if settings.execution_mode == "pending_limit":
            self._decision(
                "entry",
                "Qualified Fib setup is ready for pending-limit execution.",
                ready=True,
                **setup_details,
            )
            return setup

        if settings.entry_trigger == "touch":
            trigger = candles[-1]
            touched = trigger.low <= setup.entry <= trigger.high
            if touched:
                self._decision(
                    "entry",
                    "The live M15 candle touched the Fib entry.",
                    ready=True,
                    live_low=trigger.low,
                    live_high=trigger.high,
                    **setup_details,
                )
                return setup
            self._decision(
                "entry",
                "Qualified setup found; waiting for price to touch the Fib entry.",
                live_low=trigger.low,
                live_high=trigger.high,
                **setup_details,
            )
            return None

        # Close-based triggers use the most recent completed M15 candle.
        trigger = structure_candles[-1]
        touched = trigger.low <= setup.entry <= trigger.high

        if settings.entry_trigger == "close_back_in_direction":
            if setup.side == "BUY":
                confirmed = trigger.low <= setup.entry and trigger.close > setup.entry
            else:
                confirmed = trigger.high >= setup.entry and trigger.close < setup.entry
            if confirmed:
                self._decision(
                    "entry",
                    "The completed M15 candle confirmed the Fib entry.",
                    ready=True,
                    **setup_details,
                )
                return setup
            self._decision(
                "entry",
                "Qualified setup found; waiting for a completed M15 close back in direction.",
                completed_close=trigger.close,
                touched=touched,
                **setup_details,
            )
            return None

        if settings.entry_trigger == "directional_close":
            if setup.side == "BUY":
                confirmed = touched and trigger.close > trigger.open and trigger.close >= setup.entry
            else:
                confirmed = touched and trigger.close < trigger.open and trigger.close <= setup.entry
            if confirmed:
                self._decision(
                    "entry",
                    "The completed directional M15 candle confirmed the Fib entry.",
                    ready=True,
                    **setup_details,
                )
                return setup
            self._decision(
                "entry",
                "Qualified setup found; waiting for a directional M15 close at the Fib entry.",
                completed_open=trigger.open,
                completed_close=trigger.close,
                touched=touched,
                **setup_details,
            )
            return None

        self._decision("entry", "The configured entry trigger is not supported.", **setup_details)
        return None


# Backward-compatible alias for code created before sell support was added.
WebControlledLongFibStrategy = WebControlledFibStrategy
