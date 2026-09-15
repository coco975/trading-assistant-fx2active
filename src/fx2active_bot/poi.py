from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .fibonacci import BearishFibLevels, BullishFibLevels
from .models import Candle
from .runtime_settings import PoiSettings
from .swings import is_swing_high, is_swing_low


class PointOfInterestRule(Protocol):
    def confirms_long(self, candles: Sequence[Candle], levels: BullishFibLevels) -> bool:
        ...

    def confirms_short(self, candles: Sequence[Candle], levels: BearishFibLevels) -> bool:
        ...


class AllowAllPOI:
    """Development-only placeholder."""

    def confirms_long(self, candles: Sequence[Candle], levels: BullishFibLevels) -> bool:
        return True

    def confirms_short(self, candles: Sequence[Candle], levels: BearishFibLevels) -> bool:
        return True


@dataclass(frozen=True)
class POIEvidence:
    support_resistance: bool
    previous_swing: bool
    trendline: bool
    psychological_level: bool
    candle_confirmation: bool

    def as_dict(self) -> dict[str, bool]:
        return {
            "support_resistance": self.support_resistance,
            "previous_swing": self.previous_swing,
            "trendline": self.trendline,
            "psychological_level": self.psychological_level,
            "candle_confirmation": self.candle_confirmation,
        }


class ConfigurablePOIRule:
    """Deterministic POI heuristics controlled by the web panel."""

    def __init__(
        self,
        settings: PoiSettings,
        *,
        pip_size: float,
        tolerance_pips: float = 15.0,
        lookback: int = 80,
    ) -> None:
        if pip_size <= 0:
            raise ValueError("pip_size must be positive")
        self.settings = settings
        self.pip_size = pip_size
        self.tolerance = tolerance_pips * pip_size
        self.lookback = lookback
        self.last_evidence: POIEvidence | None = None

    def _near(self, a: float, b: float) -> bool:
        return abs(a - b) <= self.tolerance

    def _support_resistance(self, candles: Sequence[Candle], entry: float) -> bool:
        sample = candles[-self.lookback:-1]
        touches = sum(
            1
            for candle in sample
            if self._near(candle.low, entry) or self._near(candle.high, entry)
        )
        return touches >= 2

    def _previous_swing(self, candles: Sequence[Candle], entry: float) -> bool:
        start = max(2, len(candles) - self.lookback)
        end = max(start, len(candles) - 2)
        for i in range(start, end):
            if is_swing_low(candles, i) and self._near(candles[i].low, entry):
                return True
            if is_swing_high(candles, i) and self._near(candles[i].high, entry):
                return True
        return False

    def _trendline(self, candles: Sequence[Candle], entry: float, side: str) -> bool:
        if side == "BUY":
            indices = [
                i
                for i in range(2, max(2, len(candles) - 2))
                if is_swing_low(candles, i)
            ]
            prices = [candles[index].low for index in indices]
        else:
            indices = [
                i
                for i in range(2, max(2, len(candles) - 2))
                if is_swing_high(candles, i)
            ]
            prices = [candles[index].high for index in indices]

        if len(indices) < 2:
            return False
        i1, i2 = indices[-2], indices[-1]
        p1, p2 = prices[-2], prices[-1]
        slope = (p2 - p1) / (i2 - i1)
        projected = p2 + slope * ((len(candles) - 1) - i2)
        return self._near(projected, entry)

    def _psychological_level(self, entry: float) -> bool:
        major_step = 100 * self.pip_size
        nearest = round(entry / major_step) * major_step
        return self._near(nearest, entry)

    def _candle_confirmation(self, candles: Sequence[Candle], entry: float, side: str) -> bool:
        if not candles:
            return False
        candle = candles[-1]
        touched = candle.low <= entry <= candle.high
        if side == "BUY":
            return touched and candle.close > candle.open and candle.close >= entry
        return touched and candle.close < candle.open and candle.close <= entry

    def evidence(self, candles: Sequence[Candle], entry: float, side: str) -> POIEvidence:
        return POIEvidence(
            support_resistance=self._support_resistance(candles, entry),
            previous_swing=self._previous_swing(candles, entry),
            trendline=self._trendline(candles, entry, side),
            psychological_level=self._psychological_level(entry),
            candle_confirmation=self._candle_confirmation(candles, entry, side),
        )

    def _confirms(self, evidence: POIEvidence) -> bool:
        self.last_evidence = evidence
        values = evidence.as_dict()
        enabled = {
            "support_resistance": self.settings.support_resistance,
            "previous_swing": self.settings.previous_swing,
            "trendline": self.settings.trendline,
            "psychological_level": self.settings.psychological_level,
            "candle_confirmation": self.settings.candle_confirmation,
        }
        active_names = [name for name, is_enabled in enabled.items() if is_enabled]
        required = min(self.settings.min_confirmations, len(active_names))
        if required == 0:
            return True
        score = sum(1 for name in active_names if values[name])
        return score >= required

    def confirms_long(self, candles: Sequence[Candle], levels: BullishFibLevels) -> bool:
        return self._confirms(self.evidence(candles, levels.entry_78_6, "BUY"))

    def confirms_short(self, candles: Sequence[Candle], levels: BearishFibLevels) -> bool:
        return self._confirms(self.evidence(candles, levels.entry_78_6, "SELL"))
