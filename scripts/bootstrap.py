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

    from fx2active_bot.mac_bridge import find_snapshot_path, install_bridge_source

    if find_snapshot_path() is not None:
        print("[OK] macOS MT5 bridge data was detected.")
        return

    source = ROOT / "bridge" / "FX2ActiveBridge.mq5"
    print("[SETUP] Checking the running MetaTrader installation for the FX2Active bridge...")
    installed = install_bridge_source(source)
    if installed:
        print("[OK] FX2Active created its MT5 Experts folder and copied the bridge automatically.")
        for path in installed[:3]:
            print(f"     {path}")
        if len(installed) > 3:
            print(f"     ...and {len(installed) - 3} additional MT5 location(s)")
        print("One-time MT5 step still required:")
        print("  1. Open MetaEditor from MT5 and compile FX2ActiveBridge.mq5.")
        print("  2. Return to MT5 and attach FX2ActiveBridge to one chart.")
        print("  3. Enable Algo Trading and leave that chart open.")
        print("  4. Use Run system check in the FX2Active dashboard.")
    else:
        print("[WARN] FX2Active could not identify the active MT5 data folder yet.")
        print("Keep the Exness/MetaTrader 5 terminal open, then restart FX2Active.")
        print("You do not need to manually create or copy the FX2Active folder.")
        print("The dashboard will still open while MT5 setup is incomplete.")


def main() -> int:
    print("\n--- FX2Active first-run / startup checks ---")
    if sys.version_info < (3, 11):
        print(f"[ERROR] Python {sys.version.split()[0]} is too old. Python 3.11+ is required.")
        print("Install Python 3.12+, delete the .venv folder, then run the FX2Active launcher again.")
        return 1

    ensure_python_packages()
    prepare_macos_bridge()

    from fx2active_bot.system_diagnostics import run_diagnostics

    access_mode = os.environ.get("FX2ACTIVE_ACCESS_MODE", "local").strip().lower()
    host = "0.0.0.0" if access_mode == "lan" else "127.0.0.1"

    settings_path = ROOT / "config" / "runtime_settings.json"
    report = run_diagnostics(
        settings_path=settings_path,
        host=host,
        port=8080,
        include_port_check=True,
    )
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
            print("Open/prepare FX2ActiveBridge in MT5, then use Run system check in the dashboard.")
        else:
            print("Open/connect MT5, then use Run system check in the dashboard.")

    print("\n[OK] Starting FX2Active worker + dashboard...")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "run_fx2active.py")])


if __name__ == "__main__":
    raise SystemExit(main())
