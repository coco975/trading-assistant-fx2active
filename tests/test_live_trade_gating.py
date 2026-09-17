from datetime import datetime, timedelta, timezone

from fx2active_bot.config import StrategyConfig
from fx2active_bot.models import Candle
from fx2active_bot.poi import ConfigurablePOIRule, POIEvidence
from fx2active_bot.runtime_settings import PoiSettings
from fx2active_bot.strategy import DualFibStrategy


def _candle(index: int, *, low: float, high: float) -> Candle:
    midpoint = (low + high) / 2
    return Candle(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index),
        open=midpoint,
        high=high,
        low=low,
        close=midpoint,
    )


def test_candle_quality_is_not_a_hard_poi_veto() -> None:
    settings = PoiSettings(
        support_resistance=True,
        previous_swing=True,
        trendline=False,
        psychological_level=False,
        candle_confirmation=True,
        min_confirmations=2,
    )
    rule = ConfigurablePOIRule(settings, pip_size=0.01)
    evidence = POIEvidence(
        support_resistance=True,
        previous_swing=True,
        trendline=False,
        psychological_level=False,
        candle_confirmation=False,
    )

    # Both structural confirmations satisfy the configured requirement. A weak
    # candle cannot raise that requirement to three and veto the setup.
    assert rule._confirms(evidence) is True


def test_candle_quality_can_help_without_becoming_mandatory() -> None:
    settings = PoiSettings(
        support_resistance=True,
        previous_swing=True,
        trendline=False,
        psychological_level=False,
        candle_confirmation=True,
        min_confirmations=2,
    )
    rule = ConfigurablePOIRule(settings, pip_size=0.01)
    evidence = POIEvidence(
        support_resistance=True,
        previous_swing=False,
        trendline=False,
        psychological_level=False,
        candle_confirmation=True,
    )

    # Candle quality may positively contribute to the score.
    assert rule._confirms(evidence) is True


def test_structural_poi_requirement_still_applies_without_candle_bonus() -> None:
    settings = PoiSettings(
        support_resistance=True,
        previous_swing=False,
        trendline=False,
        psychological_level=False,
        candle_confirmation=True,
        min_confirmations=1,
    )
    rule = ConfigurablePOIRule(settings, pip_size=0.01)
    evidence = POIEvidence(
        support_resistance=False,
        previous_swing=False,
        trendline=False,
        psychological_level=False,
        candle_confirmation=False,
    )

    assert rule._confirms(evidence) is False


def test_dual_strategy_falls_back_to_other_valid_direction(monkeypatch) -> None:
    candles = [
        _candle(0, low=90.0, high=100.0),
        _candle(1, low=100.0, high=110.0),
        _candle(2, low=95.0, high=105.0),
    ]

    # SELL is the newer candidate but will fail its POI check. BUY is older but
    # still valid and must be considered instead of returning no setup.
    monkeypatch.setattr("fx2active_bot.strategy.latest_bullish_swing_pair", lambda *a, **k: (0, 1))
    monkeypatch.setattr("fx2active_bot.strategy.latest_bearish_swing_pair", lambda *a, **k: (1, 2))

    class DirectionalPOI:
        def confirms_long(self, candles, levels):
            return True

        def confirms_short(self, candles, levels):
            return False

    strategy = DualFibStrategy(
        StrategyConfig(timeframe="M15", pip_size=0.01),
        DirectionalPOI(),
    )

    setup = strategy.find_setup(candles, allow_buys=True, allow_sells=True)
    assert setup is not None
    assert setup.side == "BUY"
