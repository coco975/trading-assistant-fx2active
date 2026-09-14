from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError("Candle high cannot be below candle low.")
        if not self.low <= self.open <= self.high:
            raise ValueError("Open must be inside candle range.")
        if not self.low <= self.close <= self.high:
            raise ValueError("Close must be inside candle range.")
