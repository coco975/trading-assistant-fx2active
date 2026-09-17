from datetime import datetime, timezone
from types import SimpleNamespace

from fx2active_bot.controlled_strategy import WebControlledFibStrategy
from fx2active_bot.models import Candle
from fx2active_bot.runtime_settings import RuntimeSettings, RuntimeSettingsStore
from fx2active_bot.strategy import TradeSetup
from fx2active_bot.trade_executor import FX2ACTIVE_MAGIC, ExecutionResult, WindowsTradeExecutor, setup_fingerprint


class PendingMT5:
    ACCOUNT_TRADE_MODE_REAL = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_REMOVE = 8
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_PRICE_CHANGED = 10020
    TRADE_RETCODE_PRICE_OFF = 10021

    def __init__(self) -> None:
        self.positions = []
        self.orders = []
        self.sent = []
        self.checked = []
        self.tick = SimpleNamespace(bid=100.0, ask=100.1)
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=False)
        self.next_ticket = 901

    def terminal_info(self):
        return self.terminal

    def positions_get(self, symbol=None):
        if symbol is None:
            return tuple(self.positions)
        return tuple(item for item in self.positions if getattr(item, "symbol", symbol) == symbol)

    def orders_get(self, symbol=None):
        if symbol is None:
            return tuple(self.orders)
        return tuple(item for item in self.orders if getattr(item, "symbol", symbol) == symbol)

    def symbol_info_tick(self, symbol):
        return self.tick

    def order_calc_margin(self, order_type, symbol, volume, price):
        return 10.0

    def order_check(self, request):
        self.checked.append(dict(request))
        return SimpleNamespace(retcode=0, comment="Done")

    def order_send(self, request):
        request = dict(request)
        self.sent.append(request)
        if request["action"] == self.TRADE_ACTION_REMOVE:
            ticket = int(request["order"])
            self.orders = [item for item in self.orders if int(getattr(item, "ticket", 0)) != ticket]
            return SimpleNamespace(
                retcode=self.TRADE_RETCODE_DONE,
                order=ticket,
                deal=0,
                volume=0.0,
                price=0.0,
                comment="Removed",
            )

        ticket = self.next_ticket
        self.next_ticket += 1
        if request["action"] == self.TRADE_ACTION_PENDING:
            self.orders.append(
                SimpleNamespace(
                    ticket=ticket,
                    magic=FX2ACTIVE_MAGIC,
                    symbol=request["symbol"],
                    type=request["type"],
                    price_open=request["price"],
                    sl=request["sl"],
                    tp=request["tp"],
                    volume_current=request["volume"],
                )
            )
            retcode = self.TRADE_RETCODE_PLACED
        else:
            retcode = self.TRADE_RETCODE_DONE
        return SimpleNamespace(
            retcode=retcode,
            order=ticket,
            deal=0,
            volume=request.get("volume", 0.0),
            price=request.get("price", 0.0),
            comment="Done",
        )

    def last_error(self):
        return (0, "ok")


def _info():
    return SimpleNamespace(
        digits=2,
        point=0.01,
        volume_step=0.01,
        trade_stops_level=0,
        filling_mode=2,
        trade_exemode=2,
    )


def _account():
    return SimpleNamespace(trade_mode=0, trade_allowed=True, trade_expert=True, margin_free=1000.0)


def _settings():
    return RuntimeSettings(
        trading_enabled=True,
        live_execution_enabled=True,
        execution_mode="pending_limit",
        sizing_mode="fixed_lot",
        fixed_lot=0.02,
    )


def _setup(side: str) -> TradeSetup:
    if side == "BUY":
        return TradeSetup(
            side="BUY",
            timeframe="M15",
            entry=99.5,
            stop_loss=98.0,
            take_profit=102.0,
            swing_low=98.1,
            swing_high=102.0,
            reward_to_risk=1.6,
            swing_low_time="2026-09-17T10:00:00+00:00",
            swing_high_time="2026-09-17T11:00:00+00:00",
        )
    return TradeSetup(
        side="SELL",
        timeframe="M15",
        entry=101.0,
        stop_loss=102.0,
        take_profit=98.5,
        swing_low=98.5,
        swing_high=101.9,
        reward_to_risk=2.5,
        swing_low_time="2026-09-17T13:00:00+00:00",
        swing_high_time="2026-09-17T12:00:00+00:00",
    )


def _pending_order(ticket: int, setup: TradeSetup, *, magic: int = FX2ACTIVE_MAGIC):
    order_type = PendingMT5.ORDER_TYPE_BUY_LIMIT if setup.side == "BUY" else PendingMT5.ORDER_TYPE_SELL_LIMIT
    return SimpleNamespace(
        ticket=ticket,
        magic=magic,
        symbol="XAUUSD.x",
        type=order_type,
        price_open=setup.entry,
        sl=setup.stop_loss,
        tp=setup.take_profit,
        volume_current=0.02,
    )


def _execute(executor: WindowsTradeExecutor, mt5: PendingMT5, setup: TradeSetup):
    return executor.execute(
        mt5=mt5,
        settings=_settings(),
        symbol="XAUUSD.x",
        setup=setup,
        volume=0.02,
        pip_size=0.01,
        account=_account(),
        symbol_info=_info(),
    )


def test_direction_change_cancels_old_pending_then_places_replacement(tmp_path) -> None:
    mt5 = PendingMT5()
    old_setup = _setup("BUY")
    new_setup = _setup("SELL")
    mt5.orders = [_pending_order(700, old_setup)]
    executor = WindowsTradeExecutor(state_path=tmp_path / "execution_state.json")
    executor.state.record(
        setup_fingerprint("XAUUSD.x", old_setup, "pending_limit"),
        ExecutionResult(True, "placed", "Done", "old", order_ticket=700, volume=0.02, price=99.5),
    )

    result = _execute(executor, mt5, new_setup)

    assert result.ok is True
    assert result.status == "placed"
    assert mt5.sent[0]["action"] == mt5.TRADE_ACTION_REMOVE
    assert mt5.sent[0]["order"] == 700
    assert mt5.sent[1]["action"] == mt5.TRADE_ACTION_PENDING
    assert mt5.sent[1]["type"] == mt5.ORDER_TYPE_SELL_LIMIT
    assert len(mt5.orders) == 1
    assert mt5.orders[0].type == mt5.ORDER_TYPE_SELL_LIMIT


def test_changed_fib_geometry_replaces_same_direction_pending(tmp_path) -> None:
    mt5 = PendingMT5()
    old_setup = _setup("SELL")
    new_setup = TradeSetup(
        **{
            **old_setup.__dict__,
            "entry": 101.4,
            "stop_loss": 102.4,
            "swing_high": 102.3,
            "swing_high_time": "2026-09-17T14:00:00+00:00",
        }
    )
    mt5.orders = [_pending_order(701, old_setup)]
    executor = WindowsTradeExecutor(state_path=tmp_path / "execution_state.json")

    result = _execute(executor, mt5, new_setup)

    assert result.ok is True
    assert [request["action"] for request in mt5.sent] == [
        mt5.TRADE_ACTION_REMOVE,
        mt5.TRADE_ACTION_PENDING,
    ]
    assert mt5.orders[0].price_open == 101.4


def test_matching_pending_is_kept_without_resubmission(tmp_path) -> None:
    mt5 = PendingMT5()
    current = _setup("SELL")
    mt5.orders = [_pending_order(702, current)]
    executor = WindowsTradeExecutor(state_path=tmp_path / "execution_state.json")

    result = _execute(executor, mt5, current)

    assert result.ok is True
    assert result.status == "pending_active"
    assert result.order_ticket == 702
    assert mt5.sent == []


def test_manual_pending_order_is_never_cancelled(tmp_path) -> None:
    mt5 = PendingMT5()
    old_setup = _setup("BUY")
    current = _setup("SELL")
    mt5.orders = [
        _pending_order(703, old_setup, magic=FX2ACTIVE_MAGIC),
        _pending_order(999, old_setup, magic=0),
    ]
    executor = WindowsTradeExecutor(state_path=tmp_path / "execution_state.json")

    result = _execute(executor, mt5, current)

    assert result.ok is True
    removed_tickets = [request["order"] for request in mt5.sent if request["action"] == mt5.TRADE_ACTION_REMOVE]
    assert removed_tickets == [703]
    assert any(int(getattr(order, "ticket", 0)) == 999 for order in mt5.orders)


def test_pending_mode_continues_strategy_analysis_while_pending_exposure_exists(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    RuntimeSettingsStore(settings_path).save(
        RuntimeSettings(
            trading_enabled=True,
            live_execution_enabled=True,
            execution_mode="pending_limit",
            max_open_positions=1,
            poi=RuntimeSettings().poi,
        )
    )
    expected = _setup("SELL")
    monkeypatch.setattr(
        "fx2active_bot.controlled_strategy.DualFibStrategy.find_setup",
        lambda self, candles, **kwargs: expected,
    )
    candle = Candle(
        timestamp=datetime(2026, 9, 17, tzinfo=timezone.utc),
        open=100.0,
        high=102.0,
        low=98.0,
        close=100.5,
    )
    candles = [candle, candle, candle]

    strategy = WebControlledFibStrategy(settings_path, pip_size=0.01)
    result = strategy.find_setup(candles, current_open_positions=1, current_bar_is_open=True)

    assert result is expected
