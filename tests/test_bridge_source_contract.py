from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mql5_bridge_uses_utc_protocol_and_atomic_snapshot_publish() -> None:
    source = (ROOT / "bridge" / "FX2ActiveBridge.mq5").read_text(encoding="utf-8")

    assert "FX2ACTIVE_PROTOCOL_VERSION 2" in source
    assert 'BridgeVersion = "1.10"' in source
    assert "TimeGMT()" in source
    assert "TimeLocal()" not in source
    assert "SnapshotTempFile" in source
    assert "FileMove(" in source
    assert "FILE_REWRITE" in source
    assert "FILE_COMMON" in source
    assert "EventSetTimer(1)" in source


def test_live_order_submission_is_not_implemented() -> None:
    search_roots = (ROOT / "src", ROOT / "scripts")
    offenders: list[str] = []

    for search_root in search_roots:
        for path in search_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if "order_send(" in text:
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], f"Live order submission unexpectedly found in: {offenders}"
