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
            "planned_volume": 0.01,
        },
        "execution_result": None,
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
