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
    """Return the latest confirmed swing low -> swing high impulse.

    For the newest usable swing high, use the nearest confirmed swing low before
    it. This avoids drawing a Fib from an unrelated older low when several lows
    exist before the same high.
    """

    lows = [i for i in range(len(candles)) if is_swing_low(candles, i, left=left, right=right)]
    highs = [i for i in range(len(candles)) if is_swing_high(candles, i, left=left, right=right)]

    for high_index in reversed(highs):
        preceding_lows = [index for index in lows if index < high_index]
        if preceding_lows:
            return preceding_lows[-1], high_index
    return None


def latest_bearish_swing_pair(
    candles: Sequence[Candle], *, left: int = 2, right: int = 2
) -> tuple[int, int] | None:
    """Return the latest confirmed swing high -> swing low impulse.

    For the newest usable swing low, use the nearest confirmed swing high before
    it so the selected impulse is local rather than anchored to an older high.
    """

    highs = [i for i in range(len(candles)) if is_swing_high(candles, i, left=left, right=right)]
    lows = [i for i in range(len(candles)) if is_swing_low(candles, i, left=left, right=right)]

    for low_index in reversed(lows):
        preceding_highs = [index for index in highs if index < low_index]
        if preceding_highs:
            return preceding_highs[-1], low_index
    return None
