import json
import os
import time

import pytest

import fx2active_bot.mac_bridge as mac_bridge
from fx2active_bot.mac_bridge import (
    BRIDGE_PROTOCOL_VERSION,
    bridge_loss_per_one_lot,
    bridge_source_needs_compile,
    find_common_files_dirs,
    find_experts_dirs,
    find_snapshot_path,
    install_bridge_source,
    load_snapshot,
    snapshot_is_fresh,
    write_requested_symbol,
)


def valid_snapshot(**overrides):
    snapshot = {
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
        "bridge_version": "1.10",
        "heartbeat": time.time(),
        "heartbeat_utc": time.time(),
        "terminal": {"connected": True, "trade_allowed": True, "build": 1},
        "account": {"login": "1234", "trade_allowed": True},
        "symbol": {"name": "XAUUSDm", "selected": True},
        "rates": [],
    }
    snapshot.update(overrides)
    return snapshot


def test_bridge_loss_uses_tick_size_and_loss_value() -> None:
    symbol = {"trade_tick_size": 0.01, "trade_tick_value_loss": 1.0}
    assert bridge_loss_per_one_lot(symbol, 2000.0, 1999.5) == 50.0


def test_bridge_override_reads_snapshot_and_writes_requested_symbol(tmp_path, monkeypatch) -> None:
    bridge_dir = tmp_path / "FX2Active"
    bridge_dir.mkdir()
    (bridge_dir / "snapshot.json").write_text(
        json.dumps(valid_snapshot()), encoding="utf-8"
    )
    monkeypatch.setenv("FX2ACTIVE_MT5_BRIDGE_DIR", str(bridge_dir))

    assert find_snapshot_path() == bridge_dir / "snapshot.json"
    loaded, path = load_snapshot()
    assert path == bridge_dir / "snapshot.json"
    assert loaded["account"]["login"] == "1234"
    assert snapshot_is_fresh(loaded) is True

    target = write_requested_symbol("XAUUSD.x")
    assert target == bridge_dir / "requested_symbol.txt"
    assert target.read_text(encoding="utf-8").strip() == "XAUUSD.x"


def test_snapshot_rejects_outdated_bridge_protocol(tmp_path, monkeypatch) -> None:
    bridge_dir = tmp_path / "FX2Active"
    bridge_dir.mkdir()
    snapshot = valid_snapshot(protocol_version=BRIDGE_PROTOCOL_VERSION - 1)
    (bridge_dir / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setenv("FX2ACTIVE_MT5_BRIDGE_DIR", str(bridge_dir))

    with pytest.raises(RuntimeError, match="out of date"):
        load_snapshot()


def test_future_heartbeat_is_not_treated_as_fresh() -> None:
    snapshot = valid_snapshot(heartbeat_utc=time.time() + 3600)
    assert snapshot_is_fresh(snapshot) is False


def test_install_bridge_source_creates_fx2active_folder(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source" / "FX2ActiveBridge.mq5"
    source.parent.mkdir()
    source.write_text("bridge source", encoding="utf-8")
    experts = tmp_path / "terminal" / "MQL5" / "Experts"

    monkeypatch.setattr(mac_bridge, "find_experts_dirs", lambda force_refresh=False: [experts])
    installed = install_bridge_source(source)

    expected = experts / "FX2Active" / "FX2ActiveBridge.mq5"
    assert installed == [expected]
    assert expected.read_text(encoding="utf-8") == "bridge source"


def test_bridge_compile_freshness_uses_source_and_ex5_mtimes(tmp_path) -> None:
    source = tmp_path / "FX2ActiveBridge.mq5"
    compiled = tmp_path / "FX2ActiveBridge.ex5"
    source.write_text("source", encoding="utf-8")
    compiled.write_bytes(b"compiled")

    now = time.time()
    os.utime(source, (now, now))
    os.utime(compiled, (now - 10, now - 10))
    assert bridge_source_needs_compile(source) is True

    os.utime(compiled, (now + 10, now + 10))
    assert bridge_source_needs_compile(source) is False


def test_broker_branded_wine_prefix_discovers_terminal_data_dirs(tmp_path, monkeypatch) -> None:
    prefix = tmp_path / "Exness MetaTrader 5" / "wineprefix"
    terminal_root = (
        prefix
        / "drive_c"
        / "users"
        / "mac"
        / "AppData"
        / "Roaming"
        / "MetaQuotes"
        / "Terminal"
    )
    mql5 = terminal_root / "ABC123" / "MQL5"
    experts = mql5 / "Experts"
    common = terminal_root / "Common" / "Files"
    experts.mkdir(parents=True)
    common.mkdir(parents=True)

    monkeypatch.delenv("FX2ACTIVE_MT5_BRIDGE_DIR", raising=False)
    monkeypatch.setattr(mac_bridge, "_wine_prefixes", lambda force_refresh=False: (prefix,))

    assert common in find_common_files_dirs(force_refresh=True)
    assert experts in find_experts_dirs(force_refresh=True)


def test_invalid_symbol_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid MT5 symbol"):
        write_requested_symbol("XAUUSD\nBAD")
