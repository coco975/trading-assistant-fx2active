import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fx2active_bot.execution_runtime import run_execution_system  # noqa: E402


if __name__ == "__main__":
    access_mode = os.environ.get("FX2ACTIVE_ACCESS_MODE", "local").strip().lower()
    if access_mode not in {"local", "lan"}:
        access_mode = "local"

    host = "0.0.0.0" if access_mode == "lan" else "127.0.0.1"
    dashboard_pin = os.environ.get("FX2ACTIVE_DASHBOARD_PIN") if access_mode == "lan" else None

    if access_mode == "lan" and not dashboard_pin:
        raise SystemExit("LAN mode requires FX2ACTIVE_DASHBOARD_PIN")

    run_execution_system(
        ROOT,
        host=host,
        port=8080,
        access_mode=access_mode,
        dashboard_pin=dashboard_pin,
    )
