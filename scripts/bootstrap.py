from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FATAL_STARTUP_CHECKS = {
    "Python",
    "Operating system",
    "Strategy settings",
    "Local web port",
}

REQUIRED_PROJECT_FILES = (
    "pyproject.toml",
    "config/runtime_settings.json",
    "bridge/FX2ActiveBridge.mq5",
    "scripts/run_fx2active.py",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
)


def ask_yes_no(question: str, *, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please type Y or N.")


def verify_project_layout() -> bool:
    missing = [relative for relative in REQUIRED_PROJECT_FILES if not (ROOT / relative).is_file()]
    if missing:
        print("[ERROR] The FX2Active folder is incomplete. Missing:")
        for relative in missing:
            print(f"  - {relative}")
        print("Run git pull again or clone a fresh copy of the repository.")
        return False
    print("[OK] FX2Active project files are complete.")
    return True


def project_is_installed() -> bool:
    try:
        metadata.version("trading-assistant-fx2active")
        return True
    except metadata.PackageNotFoundError:
        return False


def ensure_python_packages() -> None:
    system = platform.system()
    mt5_missing = system == "Windows" and importlib.util.find_spec("MetaTrader5") is None
    project_missing = not project_is_installed()

    if not mt5_missing and not project_missing:
        print("[OK] Required Python packages are already installed.")
        return

    print("\n[SETUP] This bot needs its local Python runtime prepared.")
    if project_missing:
        print(
            "  - FX2Active project package: registers this repository inside the "
            "private .venv so the launcher can import the bot reliably."
        )
    if mt5_missing:
        print(
            "  - MetaTrader5: the Windows Python bridge used to read MT5 prices, "
            "account state and positions."
        )
    if system == "Darwin":
        print(
            "  - macOS uses the FX2Active MQL5 bridge inside MetaTrader instead of "
            "the Windows-only MetaTrader5 Python IPC package."
        )
    print("\nInstallation is limited to this bot's .venv folder, not system-wide.")
    if not ask_yes_no("Prepare the bot's required Python packages now?"):
        raise SystemExit("Setup cancelled before installing dependencies.")

    cmd = [sys.executable, "-m", "pip", "install", "-e", str(ROOT)]
    print("\nInstalling required packages...")
    subprocess.check_call(cmd)
    print("[OK] Python runtime prepared.")


def prepare_macos_bridge() -> None:
    if platform.system() != "Darwin":
        return

    from fx2active_bot.mac_bridge import (
        bridge_source_needs_compile,
        install_bridge_source,
        load_snapshot,
        snapshot_age_seconds,
        snapshot_is_fresh,
    )

    source = ROOT / "bridge" / "FX2ActiveBridge.mq5"
    try:
        installed = install_bridge_source(source)
    except Exception as exc:
        installed = []
        print(f"[WARN] Automatic MT5 bridge installation check failed: {exc}")

    if installed:
        print(f"[OK] Latest FX2ActiveBridge.mq5 installed in {len(installed)} MT5 data folder(s).")
        current_compiled = [path for path in installed if not bridge_source_needs_compile(path)]
        if current_compiled:
            print("[OK] A compiled FX2ActiveBridge.ex5 matching the installed source was detected.")
        else:
            print("[SETUP] The latest bridge source is installed but needs one MetaEditor compile.")
            print("  Open MetaEditor > Experts > FX2Active > FX2ActiveBridge.mq5 and press Compile.")
            print("  Then attach FX2ActiveBridge to one MT5 chart and enable Algo Trading.")
    else:
        print("[WARN] A MetaTrader macOS data folder was not detected automatically.")
        print("  Keep your broker's MT5 app open and run FX2Active again.")
        print("  The dashboard will still start and show the exact bridge status.")

    try:
        snapshot, path = load_snapshot()
        if snapshot_is_fresh(snapshot):
            age = snapshot_age_seconds(snapshot)
            print(f"[OK] Live macOS MT5 bridge detected at {path} ({age:.1f}s old).")
        else:
            print("[WARN] An MT5 bridge snapshot exists but is not updating yet.")
    except Exception as exc:
        print(f"[WARN] macOS MT5 bridge is not live yet: {exc}")


def main() -> int:
    print("\n--- FX2Active first-run / startup checks ---")
    if sys.version_info < (3, 11):
        print(f"[ERROR] Python {sys.version.split()[0]} is too old. Python 3.11+ is required.")
        print("Install Python 3.11+, rebuild .venv, then run the FX2Active launcher again.")
        return 1

    if not verify_project_layout():
        return 1

    try:
        ensure_python_packages()
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Python package setup failed with exit code {exc.returncode}.")
        print("Check the internet connection, then run the launcher again.")
        return 1
    except OSError as exc:
        print(f"[ERROR] Python package setup could not run: {exc}")
        return 1

    prepare_macos_bridge()

    from fx2active_bot.system_diagnostics import run_diagnostics

    access_mode = os.environ.get("FX2ACTIVE_ACCESS_MODE", "local").strip().lower()
    host = "0.0.0.0" if access_mode == "lan" else "127.0.0.1"

    settings_path = ROOT / "config" / "runtime_settings.json"
    try:
        report = run_diagnostics(
            settings_path=settings_path,
            host=host,
            port=8080,
            include_port_check=True,
        )
    except Exception as exc:
        print(f"[ERROR] Startup diagnostics crashed unexpectedly: {exc}")
        return 1

    print("\n--- System diagnosis ---")
    for check in report["checks"]:
        marker = "OK" if check["ok"] else ("WARN" if check["level"] == "warning" else "ERROR")
        print(f"[{marker}] {check['name']}: {check['message']}")

    fatal_failures = [
        check
        for check in report["checks"]
        if not check["ok"] and check["name"] in FATAL_STARTUP_CHECKS
    ]
    if fatal_failures:
        print("\nFX2Active cannot start the dashboard until the startup problem above is fixed.")
        return 1

    if not report["ready"]:
        print("\n[WARN] The dashboard will start, but MT5 is not fully ready yet.")
        if platform.system() == "Darwin":
            print("Finish the FX2ActiveBridge step in MT5, then use Run system check in the dashboard.")
        else:
            print("Open/connect MT5, then use Run system check in the dashboard.")

    print("\n[OK] Startup preflight completed. Starting FX2Active worker + dashboard...")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "run_fx2active.py")])


if __name__ == "__main__":
    raise SystemExit(main())
