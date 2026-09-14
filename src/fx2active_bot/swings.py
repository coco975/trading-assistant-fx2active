from collections.abc import Sequence

from .models import Candle


def is_swing_high(candles: Sequence[Candle], index: int, *, left: int = 2, right: int = 2) -> bool:
    if index - left < 0 or index + right >= len(candles):
        return False
    center = candles[index].high
    return (
        all(center > candles[i].high for i in range(index - left, index))
        and all(center > candles[i].high for i in range(index + 1, index + right + 1))
    )


def is_swing_low(candles: Sequence[Candle], index: int, *, left: int = 2, right: int = 2) -> bool:
    if index - left < 0 or index + right >= len(candles):
        return False
    center = candles[index].low
    return (
        all(center < candles[i].low for i in range(index - left, index))
        and all(center < candles[i].low for i in range(index + 1, index + right + 1))
    )


def latest_bullish_swing_pair(
    candles: Sequence[Candle], *, left: int = 2, right: int = 2
) -> tuple[int, int] | None:
    lows = [i for i in range(len(candles)) if is_swing_low(candles, i, left=left, right=right)]
    highs = [i for i in range(len(candles)) if is_swing_high(candles, i, left=left, right=right)]
    candidates = [(lo, hi) for lo in lows for hi in highs if lo < hi]
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[1])
