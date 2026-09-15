import json
from types import SimpleNamespace

from fx2active_bot.mac_trade_executor import MacTradeExecutor, read_order_result, write_order_command
from fx2active_bot.runtime_settings import RuntimeSettings
from fx2active_bot.trade_executor import FX2ACTIVE_MAGIC, setup_fingerprint


def trade_setup():
    return SimpleNamespace(
        side="BUY",
        entry=2500.0,
        stop_loss=2490.0,
        take_profit=2520.0,
        swing_low=2495.0,
        swing_high=2520.0,
    )


def execution_settings(**overrides):
    values = {
        "trading_enabled": True,
        "live_execution_enabled": True,
        "execution_mode": "market_on_trigger",
        "max_spread_pips": 20.0,
        "max_deviation_points": 20,
    }
    values.update(overrides)
    return RuntimeSettings(**values)


def bridge_snapshot(*, trade_mode=0, trade_allowed=True):
    return {
        "terminal": {"connected": True, "trade_allowed": trade_allowed},
        "account": {"trade_mode": trade_mode, "trade_allowed": trade_allowed},
        "fx2active_open_positions": 0,
        "fx2active_pending_orders": 0,
        "symbol": {"bid": 2500.0, "ask": 2500.1, "point": 0.01, "digits": 2},
    }


def test_order_command_contains_execution_safety_fields(tmp_path):
    target = write_order_command(
        tmp_path,
        {
            "command_id": "abc123",
            "mode": "MARKET",
            "side": "BUY",
            "symbol": "XAUUSDm",
            "volume": 0.01,
            "entry": 2500.0,
            "sl": 2490.0,
            "tp": 2520.0,
            "deviation": 20,
            "max_spread_pips": 15.0,
            "allow_live": False,
        },
    )
    text = target.read_text(encoding="utf-8")
    assert "protocol=1" in text
    assert "command_id=abc123" in text
    assert "magic=26091501" in text
    assert "allow_live=0" in text
    assert "max_spread_pips=15.0000" in text


def test_result_reader_requires_matching_command_id(tmp_path):
    path = tmp_path / "order_result.json"
    path.write_text(json.dumps({"command_id": "one", "ok": True}), encoding="utf-8")
    assert read_order_result(tmp_path, "two") is None
    assert read_order_result(tmp_path, "one")["ok"] is True


def test_mac_executor_consumes_successful_bridge_ack(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    setup = trade_setup()
    settings = execution_settings()
    snapshot = bridge_snapshot()

    executor = MacTradeExecutor(state_path=tmp_path / "state.json")
    fingerprint = setup_fingerprint("XAUUSDm", setup, settings.execution_mode)
    (tmp_path / "order_result.json").write_text(
        json.dumps(
            {
                "command_id": fingerprint,
                "ok": True,
                "status": "filled",
                "message": "Done",
                "retcode": 10009,
                "order": 123,
                "deal": 456,
                "volume": 0.01,
                "price": 2500.1,
            }
        ),
        encoding="utf-8",
    )

    result = executor.execute(
        settings=settings,
        symbol="XAUUSDm",
        setup=setup,
        volume=0.01,
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        timeout_seconds=0.1,
    )
    assert result.ok is True
    assert result.order_ticket == 123
    assert result.deal_ticket == 456

    second = executor.execute(
        settings=settings,
        symbol="XAUUSDm",
        setup=setup,
        volume=0.01,
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        timeout_seconds=0.1,
    )
    assert second.status == "duplicate"


def test_mac_executor_blocks_real_account_without_live_arm(tmp_path):
    settings = execution_settings(allow_live_account=False)
    executor = MacTradeExecutor(state_path=tmp_path / "state.json")
    result = executor.execute(
        settings=settings,
        symbol="XAUUSDm",
        setup=trade_setup(),
        volume=0.01,
        snapshot=bridge_snapshot(trade_mode=2),
        snapshot_path=tmp_path / "snapshot.json",
        timeout_seconds=0.01,
    )
    assert result.status == "blocked"
    assert not (tmp_path / "order_command.txt").exists()


def test_mac_executor_blocks_when_algo_trading_is_off(tmp_path):
    executor = MacTradeExecutor(state_path=tmp_path / "state.json")
    result = executor.execute(
        settings=execution_settings(),
        symbol="XAUUSDm",
        setup=trade_setup(),
        volume=0.01,
        snapshot=bridge_snapshot(trade_allowed=False),
        snapshot_path=tmp_path / "snapshot.json",
        timeout_seconds=0.01,
    )
    assert result.status == "blocked"
    assert not (tmp_path / "order_command.txt").exists()


def test_bridge_block_result_is_retryable_not_persisted(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    setup = trade_setup()
    settings = execution_settings()
    fingerprint = setup_fingerprint("XAUUSDm", setup, settings.execution_mode)
    (tmp_path / "order_result.json").write_text(
        json.dumps(
            {
                "command_id": fingerprint,
                "ok": False,
                "status": "blocked",
                "message": "Temporary broker pre-check block",
                "retcode": 0,
            }
        ),
        encoding="utf-8",
    )

    executor = MacTradeExecutor(state_path=tmp_path / "state.json")
    # The stale blocked result is discarded and a fresh command is issued. With
    # no bridge in this unit test, that new command times out and becomes ambiguous.
    result = executor.execute(
        settings=settings,
        symbol="XAUUSDm",
        setup=setup,
        volume=0.01,
        snapshot=bridge_snapshot(),
        snapshot_path=snapshot_path,
        timeout_seconds=0.01,
    )
    assert result.status == "ambiguous"
    assert (tmp_path / "order_command.txt").exists()


def test_mac_executor_timeout_is_persisted_as_ambiguous(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    executor = MacTradeExecutor(state_path=tmp_path / "state.json")
    kwargs = dict(
        settings=execution_settings(),
        symbol="XAUUSDm",
        setup=trade_setup(),
        volume=0.01,
        snapshot=bridge_snapshot(),
        snapshot_path=snapshot_path,
        timeout_seconds=0.01,
    )
    first = executor.execute(**kwargs)
    second = executor.execute(**kwargs)
    assert first.status == "ambiguous"
    assert second.status == "duplicate"


def test_magic_constant_matches_bridge_contract():
    assert FX2ACTIVE_MAGIC == 26091501
