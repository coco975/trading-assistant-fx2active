from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PoiSettings:
    support_resistance: bool = True
    previous_swing: bool = True
    trendline: bool = False
    psychological_level: bool = False
    candle_confirmation: bool = True
    min_confirmations: int = 1

    def __post_init__(self) -> None:
        for name in (
            "support_resistance",
            "previous_swing",
            "trendline",
            "psychological_level",
            "candle_confirmation",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be true or false")
        if isinstance(self.min_confirmations, bool) or not isinstance(self.min_confirmations, int):
            raise ValueError("min_confirmations must be an integer")
        if not 0 <= self.min_confirmations <= 5:
            raise ValueError("min_confirmations must be between 0 and 5")


@dataclass(frozen=True)
class RuntimeSettings:
    trading_enabled: bool = False
    allow_buys: bool = True
    allow_sells: bool = True
    symbol: str = ""
    timeframe: str = "M15"
    fib_enabled: bool = True
    fib_retracement: float = 0.786
    stop_buffer_pips: float = 10.0
    take_profit_mode: str = "swing_target"
    entry_trigger: str = "touch"
    max_open_positions: int = 1

    # The account owner controls position sizing from the local dashboard.
    sizing_mode: str = "risk_percent"
    risk_percent: float = 1.0
    fixed_lot: float = 0.01
    fixed_cash_risk: float = 10.0

    # Broker execution remains separately armed from the strategy master switch.
    execution_mode: str = "market_on_trigger"
    live_execution_enabled: bool = False
    allow_live_account: bool = False
    max_spread_pips: float = 0.0
    max_deviation_points: int = 20

    poi: PoiSettings = field(default_factory=PoiSettings)

    def __post_init__(self) -> None:
        for name in (
            "trading_enabled",
            "allow_buys",
            "allow_sells",
            "fib_enabled",
            "live_execution_enabled",
            "allow_live_account",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be true or false")

        if self.timeframe != "M15":
            raise ValueError("This test strategy is currently locked to M15")
        if not isinstance(self.symbol, str):
            raise ValueError("symbol must be text")
        if len(self.symbol) > 64:
            raise ValueError("symbol is too long")
        if any(character in self.symbol for character in "\r\n\x00"):
            raise ValueError("symbol contains invalid characters")

        numeric_fields = {
            "fib_retracement": self.fib_retracement,
            "stop_buffer_pips": self.stop_buffer_pips,
            "risk_percent": self.risk_percent,
            "fixed_lot": self.fixed_lot,
            "fixed_cash_risk": self.fixed_cash_risk,
            "max_spread_pips": self.max_spread_pips,
        }
        for name, value in numeric_fields.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")

        if not 0 < self.fib_retracement < 1:
            raise ValueError("fib_retracement must be between 0 and 1")
        if self.stop_buffer_pips <= 0:
            raise ValueError("stop_buffer_pips must be positive")
        if self.take_profit_mode != "swing_target":
            raise ValueError("take_profit_mode must be swing_target")
        if self.entry_trigger not in {"touch", "close_back_in_direction", "directional_close"}:
            raise ValueError("unsupported entry_trigger")
        if isinstance(self.max_open_positions, bool) or not isinstance(self.max_open_positions, int):
            raise ValueError("max_open_positions must be an integer")
        if not 1 <= self.max_open_positions <= 20:
            raise ValueError("max_open_positions must be between 1 and 20")
        if self.sizing_mode not in {"risk_percent", "fixed_lot", "fixed_cash"}:
            raise ValueError("unsupported sizing_mode")
        if not 0 < self.risk_percent <= 100:
            raise ValueError("risk_percent must be above 0 and at most 100")
        if self.fixed_lot <= 0:
            raise ValueError("fixed_lot must be positive")
        if self.fixed_cash_risk <= 0:
            raise ValueError("fixed_cash_risk must be positive")
        if self.execution_mode not in {"market_on_trigger", "pending_limit"}:
            raise ValueError("unsupported execution_mode")
        if not 0 <= self.max_spread_pips <= 10000:
            raise ValueError("max_spread_pips must be between 0 and 10000")
        if isinstance(self.max_deviation_points, bool) or not isinstance(self.max_deviation_points, int):
            raise ValueError("max_deviation_points must be an integer")
        if not 0 <= self.max_deviation_points <= 10000:
            raise ValueError("max_deviation_points must be between 0 and 10000")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSettings":
        if not isinstance(data, dict):
            raise ValueError("runtime settings must be a JSON object")
        payload = dict(data)
        poi_data = payload.pop("poi", {})
        if not isinstance(poi_data, dict):
            raise ValueError("poi settings must be a JSON object")

        # Backward compatibility with earlier dashboard settings.
        if payload.get("take_profit_mode") == "swing_high":
            payload["take_profit_mode"] = "swing_target"
        old_trigger = payload.get("entry_trigger")
        if old_trigger == "close_back_above":
            payload["entry_trigger"] = "close_back_in_direction"
        elif old_trigger == "bullish_close":
            payload["entry_trigger"] = "directional_close"

        payload.setdefault("allow_buys", True)
        payload.setdefault("allow_sells", True)
        payload.setdefault("symbol", "")
        payload.setdefault("sizing_mode", "risk_percent")
        payload.setdefault("risk_percent", 1.0)
        payload.setdefault("fixed_lot", 0.01)
        payload.setdefault("fixed_cash_risk", 10.0)
        payload.setdefault("execution_mode", "market_on_trigger")
        payload.setdefault("live_execution_enabled", False)
        payload.setdefault("allow_live_account", False)
        payload.setdefault("max_spread_pips", 0.0)
        payload.setdefault("max_deviation_points", 20)
        payload["symbol"] = str(payload["symbol"]).strip()

        return cls(**payload, poi=PoiSettings(**poi_data))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> RuntimeSettings:
        if not self.path.exists():
            settings = RuntimeSettings()
            self.save(settings)
            return settings
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeSettings.from_dict(data)

    def save(self, settings: RuntimeSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
