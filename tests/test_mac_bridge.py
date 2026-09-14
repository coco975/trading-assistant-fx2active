import json
import time

from fx2active_bot.mac_bridge import (
    bridge_loss_per_one_lot,
    find_snapshot_path,
    load_snapshot,
    snapshot_is_fresh,
    write_requested_symbol,
)


def test_bridge_loss_uses_tick_size_and_loss_value() -> None:
    symbol = {"trade_tick_size": 0.01, "trade_tick_value_loss": 1.0}
    assert bridge_loss_per_one_lot(symbol, 2000.0, 1999.5) == 50.0


def test_bridge_override_reads_snapshot_and_writes_requested_symbol(tmp_path, monkeypatch) -> None:
    bridge_dir = tmp_path / "FX2Active"
    bridge_dir.mkdir()
    snapshot = {
        "heartbeat": time.time(),
        "terminal": {"connected": True},
        "account": {"login": "1234"},
    }
    (bridge_dir / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setenv("FX2ACTIVE_MT5_BRIDGE_DIR", str(bridge_dir))

    assert find_snapshot_path() == bridge_dir / "snapshot.json"
    loaded, path = load_snapshot()
    assert path == bridge_dir / "snapshot.json"
    assert loaded["account"]["login"] == "1234"
    assert snapshot_is_fresh(loaded) is True

    target = write_requested_symbol("XAUUSD.x")
    assert target == bridge_dir / "requested_symbol.txt"
    assert target.read_text(encoding="utf-8").strip() == "XAUUSD.x"
