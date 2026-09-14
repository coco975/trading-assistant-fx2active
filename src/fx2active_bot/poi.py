from typing import Protocol, Sequence

from .fibonacci import BullishFibLevels
from .models import Candle


class PointOfInterestRule(Protocol):
    def confirms_long(self, candles: Sequence[Candle], levels: BullishFibLevels) -> bool:
        ...


class AllowAllPOI:
    """Development-only placeholder until the exact POI rules are supplied."""

    def confirms_long(self, candles: Sequence[Candle], levels: BullishFibLevels) -> bool:
        return True
