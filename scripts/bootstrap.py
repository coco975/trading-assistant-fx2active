from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


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
    mt5_missing = importlib.util.find_spec("MetaTrader5") is None
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
            "  - MetaTrader5: the Python bridge used to read MT5 prices, account "
            "state and positions."
        )
    print("\nInstallation is limited to this bot's .venv folder, not system-wide.")
    if not ask_yes_no("Prepare the bot's required Python packages now?"):
        raise SystemExit("Setup cancelled before installing dependencies.")

    cmd = [sys.executable, "-m", "pip", "install", "-e", str(ROOT)]
    print("\nInstalling required packages...")
    subprocess.check_call(cmd)
    print("[OK] Python runtime prepared.")


def main() -> int:
    print("\n--- FX2Active first-run / startup checks ---")
    if sys.version_info < (3, 11):
        print(f"[ERROR] Python {sys.version.split()[0]} is too old. Python 3.11+ is required.")
        print("Install Python 3.12, delete the .venv folder, then run START_FX2ACTIVE.bat again.")
        return 1

    ensure_python_packages()

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

    if not report["ready"]:
        print("\nThe bot is not ready to start yet.")
        print("For MT5 errors: open the intended broker's MT5 terminal and log into the account.")
        print("Then run START_FX2ACTIVE.bat again.")
        return 1

    print("\n[OK] Diagnostics passed. Starting worker + dashboard...")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "run_fx2active.py")])


if __name__ == "__main__":
    raise SystemExit(main())
