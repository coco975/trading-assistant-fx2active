from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_startup_files_exist() -> None:
    required = [
        "pyproject.toml",
        "config/runtime_settings.json",
        "bridge/FX2ActiveBridge.mq5",
        "scripts/bootstrap.py",
        "scripts/run_fx2active.py",
        "src/fx2active_bot/mac_setup.py",
        "src/fx2active_bot/trade_log.py",
        "web/index.html",
        "web/app.js",
        "web/styles.css",
        "START_FX2ACTIVE.bat",
        "START_FX2ACTIVE_MAC.command",
    ]
    missing = [relative for relative in required if not (ROOT / relative).is_file()]
    assert missing == []


def test_macos_launcher_is_offline_safe_after_python_exists() -> None:
    launcher = (ROOT / "START_FX2ACTIVE_MAC.command").read_text(encoding="utf-8")

    assert "python3.11" in launcher
    assert "ensurepip --upgrade" in launcher
    assert "pip install --upgrade pip setuptools wheel" not in launcher
    assert 'export PYTHONUNBUFFERED=1' in launcher


def test_windows_launcher_prefers_python_before_py_launcher() -> None:
    launcher = (ROOT / "START_FX2ACTIVE.bat").read_text(encoding="utf-8")

    assert launcher.index("python --version") < launcher.index("py -3 --version")
    assert 'set "PYTHONUNBUFFERED=1"' in launcher
    assert "ensurepip --upgrade" in launcher


def test_runtime_scripts_import_from_repository_source() -> None:
    for relative in ("scripts/run_fx2active.py", "scripts/run_control_panel.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert 'SRC = ROOT / "src"' in source
        assert "sys.path.insert(0, str(SRC))" in source


def test_bootstrap_has_project_preflight_and_mt5_specific_dependency_setup() -> None:
    bootstrap = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")

    assert "verify_project_layout" in bootstrap
    assert "REQUIRED_PROJECT_FILES" in bootstrap
    assert 'platform.system() != "Windows"' in bootstrap
    assert '"MetaTrader5>=5.0.45"' in bootstrap


def test_bootstrap_automates_mac_bridge_folder_and_compile_preparation() -> None:
    bootstrap = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")
    mac_setup = (ROOT / "src" / "fx2active_bot" / "mac_setup.py").read_text(encoding="utf-8")

    assert "prepare_mac_bridge" in bootstrap
    assert "created/updated the Experts/FX2Active folder" in bootstrap
    assert '"MQL5" / "Experts" / mac_bridge.BRIDGE_DIR_NAME' in mac_setup
    assert 'f"/compile:{windows_source}"' in mac_setup
    assert '"WINEPREFIX"' in mac_setup
    assert "sudo" not in mac_setup
