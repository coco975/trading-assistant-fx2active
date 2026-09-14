from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .controlled_strategy import WebControlledFibStrategy
from .models import Candle
from .runtime_settings import RuntimeSettingsStore
from .system_diagnostics import run_diagnostics
from .web_server import ControlPanelServer


class LocalRuntimeMonitor:
    """Local MT5 health monitor plus strategy evaluator.

    It reads M15 candles from the connected MT5 terminal and evaluates the current
    web-controlled BUY/SELL Fib strategy. Live order submission intentionally remains
    disabled until position sizing and final execution semantics are specified.
    """

    def __init__(self, *, settings_path: str | Path, status_path: str | Path) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.settings_path = Path(settings_path)
        self.status_path = Path(status_path)
        self.stop_event = threading.Event()

    def _write(self, payload: dict[str, Any]) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.status_path)

    @staticmethod
    def _pip_size(symbol_info: Any) -> float:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        digits = int(getattr(symbol_info, "digits", 0) or 0)
        if point <= 0:
            raise ValueError("MT5 returned an invalid point size for the symbol")
        return point * 10 if digits in {3, 5} else point

    @staticmethod
    def _candles_from_rates(rates: Any) -> list[Candle]:
        if rates is None:
            return []
        candles: list[Candle] = []
        for row in rates:
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                )
            )
        return candles

    def _snapshot(self) -> dict[str, Any]:
        settings = self.store.load()
        payload: dict[str, Any] = {
            "worker_online": True,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "trading_enabled": settings.trading_enabled,
            "allow_buys": settings.allow_buys,
            "allow_sells": settings.allow_sells,
            "symbol": settings.symbol,
            "max_open_positions": settings.max_open_positions,
            "mt5_connected": False,
            "account_connected": False,
            "open_positions": None,
            "position_limit_reached": False,
            "strategy_evaluating": False,
            "last_setup": None,
            "execution_mode": "evaluation-only",
            "message": "Worker is starting...",
        }

        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                payload["message"] = f"MT5 connection failed: {mt5.last_error()}"
                return payload

            try:
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

                if not payload["mt5_connected"] or not payload["account_connected"]:
                    payload["message"] = "MT5 is not fully connected/logged in."
                    return payload

                if not settings.symbol:
                    payload["message"] = "MT5 is online. Set the Trading Symbol on the dashboard."
                    return payload

                symbol = settings.symbol
                if not mt5.symbol_select(symbol, True):
                    payload["message"] = f"MT5 symbol '{symbol}' was not found or could not be selected."
                    return payload

                info = mt5.symbol_info(symbol)
                if info is None:
                    payload["message"] = f"No MT5 information is available for '{symbol}'."
                    return payload

                pip_size = self._pip_size(info)
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 300)
                candles = self._candles_from_rates(rates)
                if len(candles) < 20:
                    payload["message"] = f"Waiting for enough M15 history for {symbol}."
                    return payload

                payload["strategy_evaluating"] = True
                payload["pip_size"] = pip_size
                payload["last_m15_bar"] = candles[-1].timestamp.isoformat()

                strategy = WebControlledFibStrategy(self.settings_path, pip_size=pip_size)
                setup = strategy.find_setup(
                    candles,
                    current_open_positions=int(payload["open_positions"] or 0),
                )
                if setup is not None:
                    payload["last_setup"] = {
                        "side": setup.side,
                        "entry": setup.entry,
                        "stop_loss": setup.stop_loss,
                        "take_profit": setup.take_profit,
                        "reward_to_risk": setup.reward_to_risk,
                    }
                    payload["message"] = (
                        f"{symbol}: qualifying {setup.side} setup detected. "
                        "Live order submission is still disabled."
                    )
                elif not settings.trading_enabled:
                    payload["message"] = f"{symbol}: strategy worker online; trading is disabled."
                elif payload["position_limit_reached"]:
                    payload["message"] = f"{symbol}: position limit reached; no new setup is allowed."
                else:
                    payload["message"] = f"{symbol}: strategy worker online; no qualifying setup right now."
            finally:
                mt5.shutdown()
        except Exception as exc:
            payload["message"] = f"Worker health/strategy check failed: {exc}"

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
