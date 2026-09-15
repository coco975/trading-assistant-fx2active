from types import SimpleNamespace

from fx2active_bot.runtime_settings import RuntimeSettings
from fx2active_bot.trade_executor import (
    FX2ACTIVE_MAGIC,
    WindowsTradeExecutor,
    count_bot_exposure,
)


class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
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
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PRICE_CHANGED = 10020
    TRADE_RETCODE_PRICE_OFF = 10021

    def __init__(self) -> None:
        self.sent = []
        self.checked = []
        self.positions = []
        self.orders = []
        self.tick = SimpleNamespace(bid=100.0, ask=100.1)
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=False)
        self.check_retcode = 0
        self.margin_required = 10.0
        self.send_results = [
            SimpleNamespace(
                retcode=self.TRADE_RETCODE_DONE,
                order=123,
                deal=456,
                volume=0.1,
                price=100.1,
                comment="Done",
            )
        ]

    def terminal_info(self):
        return self.terminal

    def positions_get(self, symbol=None):
        return self.positions

    def orders_get(self, symbol=None):
        return self.orders

    def symbol_info_tick(self, symbol):
        return self.tick

    def order_calc_margin(self, order_type, symbol, volume, price):
        return self.margin_required

    def order_check(self, request):
        self.checked.append(dict(request))
        return SimpleNamespace(retcode=self.check_retcode, comment="Done" if self.check_retcode == 0 else "bad")

    def order_send(self, request):
        self.sent.append(dict(request))
        if not self.send_results:
            return None
        return self.send_results.pop(0)

    def last_error(self):
        return (0, "ok")


def setup(side="BUY"):
    if side == "BUY":
        return SimpleNamespace(
            side="BUY",
            entry=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            swing_low=99.5,
            swing_high=102.0,
        )
    return SimpleNamespace(
        side="SELL",
        entry=101.0,
        stop_loss=102.0,
        take_profit=99.0,
        swing_low=99.0,
        swing_high=101.5,
    )


def info(**overrides):
    values = {
        "digits": 2,
        "point": 0.01,
        "trade_stops_level": 0,
        "filling_mode": 2,
        "trade_exemode": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def account(*, real=False, margin_free=1000.0):
    return SimpleNamespace(
        trade_mode=2 if real else 0,
        trade_allowed=True,
        margin_free=margin_free,
    )


def settings(**overrides):
    values = {
        "trading_enabled": True,
        "live_execution_enabled": True,
        "allow_live_account": False,
        "execution_mode": "market_on_trigger",
        "max_open_positions": 1,
        "max_spread_pips": 0.0,
        "max_deviation_points": 20,
    }
    values.update(overrides)
    return RuntimeSettings(**values)


def execute(executor, mt5, *, cfg=None, trade=None, acct=None, symbol_info=None):
    return executor.execute(
        mt5=mt5,
        settings=cfg or settings(),
        symbol="XAUUSDm",
        setup=trade or setup("BUY"),
        volume=0.1,
        pip_size=0.01,
        account=acct or account(),
        symbol_info=symbol_info or info(),
    )


def test_market_buy_runs_order_check_then_order_send(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5)

    assert result.ok is True
    assert result.status == "filled"
    assert result.order_ticket == 123
    assert len(mt5.checked) == 1
    assert len(mt5.sent) == 1
    request = mt5.sent[0]
    assert request["action"] == mt5.TRADE_ACTION_DEAL
    assert request["type"] == mt5.ORDER_TYPE_BUY
    assert request["price"] == 100.1
    assert request["sl"] == 99.0
    assert request["tp"] == 102.0
    assert request["magic"] == FX2ACTIVE_MAGIC


def test_pending_sell_uses_limit_order_at_fib_price(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(
        executor,
        mt5,
        cfg=settings(execution_mode="pending_limit"),
        trade=setup("SELL"),
    )

    assert result.ok is True
    request = mt5.sent[0]
    assert request["action"] == mt5.TRADE_ACTION_PENDING
    assert request["type"] == mt5.ORDER_TYPE_SELL_LIMIT
    assert request["price"] == 101.0
    assert request["type_filling"] == mt5.ORDER_FILLING_RETURN


def test_execution_disabled_never_checks_or_sends(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5, cfg=settings(live_execution_enabled=False))
    assert result.status == "disabled"
    assert mt5.checked == []
    assert mt5.sent == []


def test_terminal_autotrading_off_blocks_before_broker_request(tmp_path):
    mt5 = FakeMT5()
    mt5.terminal = SimpleNamespace(connected=True, trade_allowed=False, tradeapi_disabled=False)
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5)
    assert result.status == "blocked"
    assert mt5.checked == []
    assert mt5.sent == []


def test_external_python_api_block_is_detected(tmp_path):
    mt5 = FakeMT5()
    mt5.terminal = SimpleNamespace(connected=True, trade_allowed=True, tradeapi_disabled=True)
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5)
    assert result.status == "blocked"
    assert "Python" in result.message
    assert mt5.sent == []


def test_real_account_is_blocked_until_explicitly_allowed(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5, acct=account(real=True))

    assert result.ok is False
    assert result.status == "blocked"
    assert mt5.sent == []


def test_real_account_can_execute_when_double_armed(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(
        executor,
        mt5,
        cfg=settings(allow_live_account=True),
        acct=account(real=True),
    )
    assert result.ok is True
    assert len(mt5.sent) == 1


def test_duplicate_setup_is_not_submitted_twice(tmp_path):
    mt5 = FakeMT5()
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    first = execute(executor, mt5)
    second = execute(executor, mt5)
    assert first.ok is True
    assert second.status == "duplicate"
    assert len(mt5.sent) == 1


def test_spread_guard_blocks_before_order_check(tmp_path):
    mt5 = FakeMT5()
    mt5.tick = SimpleNamespace(bid=100.0, ask=100.5)
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5, cfg=settings(max_spread_pips=10.0))
    assert result.status == "blocked"
    assert mt5.checked == []
    assert mt5.sent == []


def test_order_check_failure_never_calls_order_send(tmp_path):
    mt5 = FakeMT5()
    mt5.check_retcode = 10016
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5)
    assert result.status == "blocked"
    assert len(mt5.checked) >= 1
    assert mt5.sent == []


def test_insufficient_margin_blocks_before_order_check(tmp_path):
    mt5 = FakeMT5()
    mt5.margin_required = 200.0
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5, acct=account(margin_free=100.0))
    assert result.status == "blocked"
    assert "margin" in result.message.lower()
    assert mt5.checked == []
    assert mt5.sent == []


def test_broker_stop_distance_blocks_invalid_order(tmp_path):
    mt5 = FakeMT5()
    tight = SimpleNamespace(
        side="BUY",
        entry=100.0,
        stop_loss=100.05,
        take_profit=100.15,
        swing_low=99.9,
        swing_high=100.15,
    )
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5, trade=tight, symbol_info=info(trade_stops_level=10))
    assert result.status == "blocked"
    assert mt5.sent == []


def test_safe_price_retry_refreshes_market_price_once(tmp_path):
    mt5 = FakeMT5()
    mt5.send_results = [
        SimpleNamespace(
            retcode=mt5.TRADE_RETCODE_PRICE_CHANGED,
            order=0,
            deal=0,
            volume=0.0,
            price=0.0,
            comment="Price changed",
        ),
        SimpleNamespace(
            retcode=mt5.TRADE_RETCODE_DONE,
            order=321,
            deal=654,
            volume=0.1,
            price=100.2,
            comment="Done",
        ),
    ]
    ticks = [
        SimpleNamespace(bid=100.0, ask=100.1),
        SimpleNamespace(bid=100.1, ask=100.2),
    ]
    mt5.symbol_info_tick = lambda symbol: ticks.pop(0) if ticks else SimpleNamespace(bid=100.1, ask=100.2)

    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    result = execute(executor, mt5)
    assert result.ok is True
    assert len(mt5.sent) == 2
    assert mt5.sent[1]["price"] == 100.2


def test_ambiguous_none_result_is_persisted_and_not_retried(tmp_path):
    mt5 = FakeMT5()
    mt5.send_results = []
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    first = execute(executor, mt5)
    second = execute(executor, mt5)
    assert first.status == "ambiguous"
    assert second.status == "duplicate"
    assert len(mt5.sent) == 1


def test_definitive_broker_rejection_is_persisted(tmp_path):
    mt5 = FakeMT5()
    mt5.send_results = [
        SimpleNamespace(
            retcode=10030,
            order=0,
            deal=0,
            volume=0.0,
            price=0.0,
            comment="Rejected",
        )
    ]
    executor = WindowsTradeExecutor(state_path=tmp_path / "state.json")
    first = execute(executor, mt5)
    second = execute(executor, mt5)
    assert first.status == "rejected"
    assert second.status == "duplicate"
    assert len(mt5.sent) == 1


def test_bot_exposure_ignores_manual_positions_and_orders():
    mt5 = FakeMT5()
    mt5.positions = [SimpleNamespace(magic=0), SimpleNamespace(magic=FX2ACTIVE_MAGIC)]
    mt5.orders = [SimpleNamespace(magic=123), SimpleNamespace(magic=FX2ACTIVE_MAGIC)]
    assert count_bot_exposure(mt5, "XAUUSDm") == (1, 1)
