from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mql5_bridge_uses_utc_protocol_atomic_publish_execution_and_history() -> None:
    source = (ROOT / "bridge" / "FX2ActiveBridge.mq5").read_text(encoding="utf-8")

    assert "FX2ACTIVE_PROTOCOL_VERSION 2" in source
    assert "FX2ACTIVE_ORDER_PROTOCOL 1" in source
    assert "FX2ACTIVE_MAGIC 26091501" in source
    assert 'BridgeVersion = "1.23"' in source
    assert '#property version   "1.23"' in source
    assert "TimeGMT()" in source
    assert "TimeLocal()" not in source
    assert "SnapshotTempFile" in source
    assert "OrderCommandFile" in source
    assert "OrderResultFile" in source
    assert "LastCommandFile" in source
    assert "BlockCommand(" in source
    assert 'PublishOrderResult(command_id,false,"blocked"' in source
    assert "OrderCheck(" in source
    assert "OrderSend(" in source
    assert "TRADE_RETCODE_DONE" in source
    assert "ACCOUNT_TRADE_MODE_REAL" in source
    assert "ACCOUNT_TRADE_EXPERT" in source
    assert 'CommandValue(text,"max_exposure")' in source
    assert "CountFX2ActivePositions()+CountFX2ActiveOrders()" in source
    assert "SYMBOL_VOLUME_MIN" in source
    assert "SYMBOL_VOLUME_MAX" in source
    assert "SYMBOL_VOLUME_STEP" in source
    assert "HistorySelect(" in source
    assert "HistoryDealsTotal()" in source
    assert "DEAL_ENTRY_OUT" in source
    assert "DEAL_PROFIT" in source
    assert "DEAL_COMMISSION" in source
    assert "DEAL_SWAP" in source
    assert "closed_trades" in source
    assert "FileMove(" in source
    assert "FILE_REWRITE" in source
    assert "FILE_COMMON" in source
    assert "EventSetTimer(1)" in source

    order_check_index = source.index("OrderCheck(request,check)")
    duplicate_marker_index = source.index("WriteWholeText(LastCommandFile,command_id")
    order_send_index = source.index("OrderSend(request,result)")
    assert order_check_index < duplicate_marker_index < order_send_index


def test_python_bridge_version_matches_mql_source() -> None:
    from fx2active_bot.mac_bridge import BRIDGE_SOURCE_VERSION

    assert BRIDGE_SOURCE_VERSION == "1.23"


def test_python_live_execution_is_isolated_to_trade_executor() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if "order_send(" in text and path.name != "trade_executor.py":
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], f"Unexpected Python order_send path found in: {offenders}"


def test_live_execution_defaults_remain_disarmed() -> None:
    settings = (ROOT / "config" / "runtime_settings.json").read_text(encoding="utf-8")
    assert '"live_execution_enabled": false' in settings
    assert '"allow_live_account": false' in settings
