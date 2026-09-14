from __future__ import annotations

import json
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_settings import RuntimeSettingsStore
from .system_diagnostics import run_diagnostics
from .web_server import ControlPanelServer


class LocalRuntimeMonitor:
    """Keep a lightweight heartbeat/status file for the local dashboard.

    This process verifies MT5 connectivity and reflects the current web-controlled
    strategy state. It intentionally does not place live orders yet; execution
    remains disabled until the exact symbol/sizing/order-entry rules are supplied.
    """

    def __init__(self, *, settings_path: str | Path, status_path: str | Path) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.status_path = Path(status_path)
        self.stop_event = threading.Event()

    def _write(self, payload: dict[str, Any]) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.status_path)

    def _snapshot(self) -> dict[str, Any]:
        settings = self.store.load()
        payload: dict[str, Any] = {
            "worker_online": True,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "trading_enabled": settings.trading_enabled,
            "allow_buys": settings.allow_buys,
            "allow_sells": settings.allow_sells,
            "max_open_positions": settings.max_open_positions,
            "mt5_connected": False,
            "account_connected": False,
            "open_positions": None,
            "execution_mode": "strategy-control-only",
            "message": "Worker running. Live order execution is not enabled yet.",
        }

        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                payload["message"] = f"Worker running, but MT5 connection failed: {mt5.last_error()}"
                return payload

            terminal = mt5.terminal_info()
            account = mt5.account_info()
            payload["mt5_connected"] = bool(getattr(terminal, "connected", False)) if terminal else False
            payload["account_connected"] = account is not None
            if account is not None:
                login = str(getattr(account, "login", ""))
                payload["account_login_masked"] = (
                    "*" * max(0, len(login) - 4) + login[-4:] if login else None
                )
                payload["account_server"] = getattr(account, "server", None)
                payload["trade_allowed"] = bool(getattr(account, "trade_allowed", True))
            positions = mt5.positions_get()
            payload["open_positions"] = len(positions) if positions is not None else 0
            payload["position_limit_reached"] = (
                payload["open_positions"] >= settings.max_open_positions
            )
            if payload["mt5_connected"] and payload["account_connected"]:
                payload["message"] = "MT5 and strategy worker are online."
            mt5.shutdown()
        except Exception as exc:
            payload["message"] = f"Worker health check failed: {exc}"

        return payload

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._write(self._snapshot())
            except Exception as exc:
                self._write(
                    {
                        "worker_online": True,
                        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                        "mt5_connected": False,
                        "message": f"Runtime monitor error: {exc}",
                    }
                )
            self.stop_event.wait(3.0)

    def stop(self) -> None:
        self.stop_event.set()


def run_local_system(root: str | Path, *, host: str = "127.0.0.1", port: int = 8080) -> None:
    root = Path(root)
    settings_path = root / "config" / "runtime_settings.json"
    status_path = root / "data" / "runtime" / "system_status.json"
    diagnostics_path = root / "data" / "runtime" / "diagnostics.json"

    diagnostics = run_diagnostics(
        settings_path=settings_path,
        host=host,
        port=port,
        include_port_check=False,
    )
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")

    monitor = LocalRuntimeMonitor(settings_path=settings_path, status_path=status_path)
    thread = threading.Thread(target=monitor.run, name="fx2active-runtime-monitor", daemon=True)
    thread.start()

    url = f"http://{host}:{port}"
    print("\n================================================")
    print(" FX2Active is running locally")
    print("================================================")
    print(f" Dashboard: {url}")
    print(" Keep this window open while the bot is running.")
    print(" Press Ctrl+C to stop the local system.")
    print("================================================\n")

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    server = ControlPanelServer(
        settings_path=settings_path,
        status_path=status_path,
        diagnostics_path=diagnostics_path,
        web_root=root / "web",
        host=host,
        port=port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FX2Active...")
    finally:
        monitor.stop()
