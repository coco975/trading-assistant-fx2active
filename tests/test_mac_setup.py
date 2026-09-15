from pathlib import Path

import fx2active_bot.mac_setup as mac_setup


def _browser_installed_mt5(tmp_path: Path) -> tuple[Path, Path]:
    prefix = tmp_path / "Library" / "Application Support" / "broker-wrapper"
    install_root = prefix / "drive_c" / "Program Files" / "Exness MetaTrader 5"
    install_root.mkdir(parents=True)
    (install_root / "terminal64.exe").write_bytes(b"terminal")
    (install_root / "metaeditor64.exe").write_bytes(b"editor")
    return prefix, install_root


def test_web_installed_mt5_is_found_before_mql5_exists(tmp_path, monkeypatch):
    prefix, install_root = _browser_installed_mt5(tmp_path)
    assert not (install_root / "MQL5").exists()

    monkeypatch.setattr(
        mac_setup,
        "discover_wine_prefixes",
        lambda force_refresh=False: [prefix],
    )

    assert mac_setup.discover_mt5_install_roots(force_refresh=True) == [install_root]


def test_bridge_setup_creates_missing_experts_tree_itself(tmp_path):
    _, install_root = _browser_installed_mt5(tmp_path)
    source = tmp_path / "FX2ActiveBridge.mq5"
    source.write_text("bridge source", encoding="utf-8")

    target = mac_setup._copy_bridge_to_install_root(source, install_root)

    assert target == install_root / "MQL5" / "Experts" / "FX2Active" / "FX2ActiveBridge.mq5"
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "bridge source"


def test_windows_path_conversion_for_metaeditor_compile(tmp_path):
    prefix, install_root = _browser_installed_mt5(tmp_path)
    source = install_root / "MQL5" / "Experts" / "FX2Active" / "FX2ActiveBridge.mq5"
    source.parent.mkdir(parents=True)
    source.write_text("bridge", encoding="utf-8")

    windows_path = mac_setup._windows_path(source, prefix)

    assert windows_path == (
        "C:\\Program Files\\Exness MetaTrader 5\\MQL5\\Experts\\FX2Active\\FX2ActiveBridge.mq5"
    )


def test_prepare_mac_bridge_does_not_require_existing_experts_folder(tmp_path, monkeypatch):
    prefix, install_root = _browser_installed_mt5(tmp_path)
    source = tmp_path / "source" / "FX2ActiveBridge.mq5"
    source.parent.mkdir()
    source.write_text("latest bridge", encoding="utf-8")

    monkeypatch.setattr(mac_setup, "find_mt5_apps", lambda: [])
    monkeypatch.setattr(
        mac_setup,
        "discover_wine_prefixes",
        lambda force_refresh=False: [prefix],
    )
    monkeypatch.setattr(
        mac_setup,
        "discover_mt5_install_roots",
        lambda force_refresh=False: [install_root],
    )
    monkeypatch.setattr(mac_setup.mac_bridge, "install_bridge_source", lambda source_path: [])
    monkeypatch.setattr(
        mac_setup,
        "try_compile_bridge_source",
        lambda target, prefixes, apps: (False, "compile unavailable in unit test"),
    )

    report = mac_setup.prepare_mac_bridge(source)

    expected = install_root / "MQL5" / "Experts" / "FX2Active" / "FX2ActiveBridge.mq5"
    assert report.installed_sources == [expected]
    assert expected.read_text(encoding="utf-8") == "latest bridge"
    assert any("compile unavailable" in warning for warning in report.warnings)
