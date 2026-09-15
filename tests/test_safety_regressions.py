from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from fx2active_bot.controlled_strategy import WebControlledFibStrategy
from fx2active_bot.models import Candle
from fx2active_bot.runtime_settings import RuntimeSettings, RuntimeSettingsStore
from fx2active_bot.strategy import TradeSetup
from fx2active_bot.swings import latest_bullish_swing_pair
from fx2active_bot.trade_executor import (
    FX2ACTIVE_MAGIC,
    ExecutionStateStore,
    WindowsTradeExecutor,
    setup_fingerprint,
)


def _candle(index: int, low: float, high: float) -> Candle:
    middle = (low + high) / 2
    return Candle(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index),
        open=middle,
        high=high,
        low=low,
        close=middle,
    )


def test_latest_bullish_pair_uses_nearest_preceding_low() -> None:
    lows = [10, 9, 5, 9, 8, 6, 8, 9, 10, 9, 8]
    highs = [11, 10, 9, 11, 10, 9, 10, 12, 15, 12, 11]
    candles = [_candle(i, low, high) for i, (low, high) in enumerate(zip(lows, highs))]

    assert latest_bullish_swing_pair(candles) == (5, 8)


def test_live_m15_bar_is_not_used_for_structure_or_close_confirmation(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    RuntimeSettingsStore(settings_path).save(
        RuntimeSettings(
            trading_enabled=True,
            entry_trigger="directional_close",
            execution_mode="market_on_trigger",
            poi=RuntimeSettings().poi,
        )
    )

    setup = TradeSetup(
        side="BUY",
        timeframe="M15",
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        swing_low=95.0,
        swing_high=120.0,
        reward_to_risk=2.0,
    )
    seen_lengths: list[int] = []

    def fake_find_setup(self, candles, **kwargs):
        seen_lengths.append(len(candles))
        return setup

    monkeypatch.setattr("fx2active_bot.controlled_strategy.DualFibStrategy.find_setup", fake_find_setup)

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(base, 105.0, 106.0, 104.0, 105.0),
        # Completed candle touches 100 and closes bullish above it.
        Candle(base + timedelta(minutes=15), 99.0, 104.0, 98.0, 103.0),
        # Live candle would fail confirmation, but must not be treated as a close.
        Candle(base + timedelta(minutes=30), 103.0, 104.0, 99.0, 100.0),
    ]

    strategy = WebControlledFibStrategy(settings_path, pip_size=0.01)
    result = strategy.find_setup(candles, current_bar_is_open=True)

    assert seen_lengths == [2]
    assert result is setup


def test_corrupt_execution_state_fails_closed(tmp_path) -> None:
    path = tmp_path / "execution_state.json"
    path.write_text("{not-json", encoding="utf-8")
    store = ExecutionStateStore(path)

    with pytest.raises(RuntimeError, match="execution-state file is unreadable"):
        store.contains("anything")


def test_setup_fingerprint_distinguishes_new_swings_at_same_prices() -> None:
    common = dict(
        side="BUY",
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        swing_low=95.0,
        swing_high=120.0,
    )
    first = SimpleNamespace(
        **common,
        swing_low_time="2026-01-01T10:00:00+00:00",
        swing_high_time="2026-01-01T11:00:00+00:00",
    )
    second = SimpleNamespace(
        **common,
        swing_low_time="2026-02-01T10:00:00+00:00",
        swing_high_time="2026-02-01T11:00:00+00:00",
    )

    assert setup_fingerprint("XAUUSDm", first, "market_on_trigger") != setup_fingerprint(
        "XAUUSDm", second, "market_on_trigger"
    )


class ExposureMT5:
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self) -> None:
        self.positions = [SimpleNamespace(magic=FX2ACTIVE_MAGIC, symbol="EURUSD")]
        self.orders = []

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=False)

    def positions_get(self, symbol=None):
        if symbol is None:
            return tuple(self.positions)
        return tuple(item for item in self.positions if item.symbol == symbol)

    def orders_get(self, symbol=None):
        if symbol is None:
            return tuple(self.orders)
        return tuple(item for item in self.orders if getattr(item, "symbol", None) == symbol)

    def last_error(self):
        return (0, "OK")


def _setup_namespace():
    return SimpleNamespace(
        side="BUY",
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        swing_low=95.0,
        swing_high=120.0,
    )


def test_windows_executor_enforces_global_bot_exposure_across_symbols(tmp_path) -> None:
    mt5 = ExposureMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    settings = RuntimeSettings(
        trading_enabled=True,
        live_execution_enabled=True,
        max_open_positions=1,
    )
    account = SimpleNamespace(trade_mode=0, trade_allowed=True, trade_expert=True)

    result = executor.execute(
        mt5=mt5,
        settings=settings,
        symbol="XAUUSDm",
        setup=_setup_namespace(),
        volume=0.01,
        pip_size=0.01,
        account=account,
        symbol_info=SimpleNamespace(point=0.01, digits=2),
    )

    assert result.status == "blocked"
    assert "limit reached" in result.message.lower()


def test_windows_executor_blocks_when_account_expert_permission_is_off(tmp_path) -> None:
    mt5 = ExposureMT5()
    mt5.positions = []
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    settings = RuntimeSettings(trading_enabled=True, live_execution_enabled=True)
    account = SimpleNamespace(trade_mode=0, trade_allowed=True, trade_expert=False)

    result = executor.execute(
        mt5=mt5,
        settings=settings,
        symbol="XAUUSDm",
        setup=_setup_namespace(),
        volume=0.01,
        pip_size=0.01,
        account=account,
        symbol_info=SimpleNamespace(point=0.01, digits=2),
    )

    assert result.status == "blocked"
    assert "automated trading" in result.message.lower()


def test_execution_switches_require_real_booleans() -> None:
    with pytest.raises(ValueError, match="live_execution_enabled must be true or false"):
        RuntimeSettings.from_dict({"live_execution_enabled": "false"})
    with pytest.raises(ValueError, match="allow_live_account must be true or false"):
        RuntimeSettings.from_dict({"allow_live_account": 1})


def test_non_finite_risk_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="risk_percent must be finite"):
        RuntimeSettings(risk_percent=float("nan"))
