from __future__ import annotations

import importlib.util
import subprocess
import sys
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


def ensure_python_packages() -> None:
    missing: list[str] = []
    if importlib.util.find_spec("MetaTrader5") is None:
        missing.append("MetaTrader5")

    if not missing:
        print("[OK] Required Python packages are already installed.")
        return

    print("\n[MISSING] Required Python package(s):")
    for name in missing:
        if name == "MetaTrader5":
            print("  - MetaTrader5: the official Python bridge used to read MT5 prices, account state and positions.")
    print("\nThese packages are installed only inside this bot's .venv folder, not system-wide.")
    if not ask_yes_no("Install the missing package(s) now?"):
        raise SystemExit("Setup cancelled before installing dependencies.")

    cmd = [sys.executable, "-m", "pip", "install", "-e", str(ROOT)]
    print("\nInstalling required packages...")
    subprocess.check_call(cmd)
    print("[OK] Python dependencies installed.")


def main() -> int:
    print("\n--- FX2Active first-run / startup checks ---")
    if sys.version_info < (3, 11):
        print(f"[ERROR] Python {sys.version.split()[0]} is too old. Python 3.11+ is required.")
        return 1

    ensure_python_packages()

    from fx2active_bot.system_diagnostics import run_diagnostics

    settings_path = ROOT / "config" / "runtime_settings.json"
    report = run_diagnostics(settings_path=settings_path, include_port_check=True)
    print("\n--- System diagnosis ---")
    for check in report["checks"]:
        marker = "OK" if check["ok"] else ("WARN" if check["level"] == "warning" else "ERROR")
        print(f"[{marker}] {check['name']}: {check['message']}")

    if not report["ready"]:
        print("\nThe bot is not ready to start yet.")
        print("Fix the ERROR item(s) above, then run START_FX2ACTIVE.bat again.")
        return 1

    print("\n[OK] Diagnostics passed. Starting local worker + dashboard...")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "run_fx2active.py")])


if __name__ == "__main__":
    raise SystemExit(main())
