from datetime import datetime, timezone
from types import SimpleNamespace

from fx2active_bot.execution_runtime import ExecutionRuntimeMonitor
from fx2active_bot.trade_executor import FX2ACTIVE_MAGIC


class FakeMT5History:
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3
    DEAL_ENTRY_INOUT = 2
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_REASON_SL = 4
    DEAL_REASON_TP = 5
    DEAL_REASON_EXPERT = 3
    DEAL_REASON_CLIENT = 0
    DEAL_REASON_MOBILE = 1
    DEAL_REASON_WEB = 2

    def history_deals_get(self, start, end):
        assert start < end
        return (
            # FX2Active BUY closing at TP: closing deal itself is SELL.
            SimpleNamespace(
                magic=FX2ACTIVE_MAGIC,
                entry=self.DEAL_ENTRY_OUT,
                type=self.DEAL_TYPE_SELL,
                reason=self.DEAL_REASON_TP,
                ticket=101,
                position_id=99,
                time=int(datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc).timestamp()),
                symbol="XAUUSDm",
                price=2520.0,
                volume=0.01,
                profit=20.0,
                commission=-0.25,
                swap=-0.10,
                fee=0.0,
            ),
            # Manual trade must not appear.
            SimpleNamespace(
                magic=0,
                entry=self.DEAL_ENTRY_OUT,
                type=self.DEAL_TYPE_BUY,
                reason=self.DEAL_REASON_SL,
                ticket=102,
                position_id=100,
                time=1,
                symbol="EURUSD",
                price=1.0,
                volume=0.1,
                profit=-5.0,
                commission=0.0,
                swap=0.0,
                fee=0.0,
            ),
        )


def test_windows_closed_trade_history_is_fx2active_only_and_net_of_costs():
    closed = ExecutionRuntimeMonitor._windows_closed_trades(FakeMT5History())

    assert len(closed) == 1
    trade = closed[0]
    assert trade["deal_ticket"] == 101
    assert trade["position_id"] == 99
    assert trade["symbol"] == "XAUUSDm"
    assert trade["side"] == "BUY"
    assert trade["close_reason"] == "Take Profit"
    assert trade["profit"] == 20.0
    assert trade["commission"] == -0.25
    assert trade["swap"] == -0.10
    assert trade["net_profit"] == 19.65
