from fx2active_bot.trade_log import TradeLogStore


def sample_status():
    return {
        "heartbeat_at": "2026-09-15T21:45:00+00:00",
        "symbol": "XAUUSDm",
        "last_setup": {
            "side": "BUY",
            "entry": 2500.0,
            "stop_loss": 2490.0,
            "take_profit": 2520.0,
            "swing_low": 2495.0,
            "swing_high": 2520.0,
            "swing_low_time": "2026-09-15T19:00:00+00:00",
            "swing_high_time": "2026-09-15T20:00:00+00:00",
            "planned_volume": 0.01,
        },
        "execution_result": None,
        "closed_trades": [],
    }


def test_trade_log_records_setup_once(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    status = sample_status()

    store.capture_status(status)
    store.capture_status(status)

    events = store.read()
    assert len(events) == 1
    assert events[0]["event"] == "Setup"
    assert events[0]["symbol"] == "XAUUSDm"
    assert events[0]["side"] == "BUY"
    assert events[0]["price"] == 2500.0
    assert events[0]["status"] == "Detected"


def test_trade_log_records_execution_result_once(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    status = sample_status()
    status["execution_result"] = {
        "fingerprint": "abc123",
        "status": "filled",
        "message": "Done",
        "retcode": 10009,
        "order_ticket": 123,
        "deal_ticket": 456,
        "volume": 0.01,
        "price": 2500.1,
    }

    store.capture_status(status)
    store.capture_status(status)

    events = store.read()
    assert len(events) == 2
    execution = events[0]
    assert execution["event"] == "Execution"
    assert execution["status"] == "filled"
    assert execution["order_ticket"] == 123
    assert execution["deal_ticket"] == 456
    assert execution["price"] == 2500.1


def test_trade_log_records_closed_trade_net_pnl_once(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    status = sample_status()
    status["closed_trades"] = [
        {
            "deal_ticket": 9001,
            "position_id": 8001,
            "timestamp_utc": "2026-09-15T21:50:00+00:00",
            "symbol": "XAUUSDm",
            "side": "BUY",
            "price": 2520.0,
            "volume": 0.01,
            "profit": 20.0,
            "commission": -0.25,
            "swap": 0.0,
            "fee": 0.0,
            "net_profit": 19.75,
            "close_reason": "Take Profit",
        }
    ]

    store.capture_status(status)
    store.capture_status(status)

    events = store.read()
    closed = next(event for event in events if event["event"] == "Closed")
    assert closed["deal_ticket"] == 9001
    assert closed["status"] == "Profit"
    assert closed["net_profit"] == 19.75
    assert closed["close_reason"] == "Take Profit"
    assert sum(event["event"] == "Closed" for event in events) == 1


def test_trade_log_marks_closed_loss(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    status = sample_status()
    status["closed_trades"] = [
        {
            "deal_ticket": 9002,
            "timestamp_utc": "2026-09-15T21:55:00+00:00",
            "symbol": "XAUUSDm",
            "side": "SELL",
            "price": 2510.0,
            "volume": 0.01,
            "net_profit": -8.5,
            "close_reason": "Stop Loss",
        }
    ]
    store.capture_status(status)

    closed = next(event for event in store.read() if event["event"] == "Closed")
    assert closed["status"] == "Loss"


def test_trade_log_ignores_disabled_and_duplicate_execution_states(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    status = sample_status()
    for state in ("disabled", "duplicate"):
        status["execution_result"] = {
            "fingerprint": "abc123",
            "status": state,
        }
        store.capture_status(status)

    events = store.read()
    assert len(events) == 1
    assert events[0]["event"] == "Setup"


def test_trade_log_clear_removes_history(tmp_path):
    store = TradeLogStore(tmp_path / "trade_log.json")
    store.capture_status(sample_status())
    assert store.read()

    store.clear()

    assert store.read() == []
