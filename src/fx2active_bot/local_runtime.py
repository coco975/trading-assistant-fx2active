from __future__ import annotations

import ipaddress
import json
import socket
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .controlled_strategy import WebControlledFibStrategy
from .models import Candle
from .position_sizing import calculate_position_size
from .runtime_settings import RuntimeSettingsStore
from .system_diagnostics import run_diagnostics
from .web_server import ControlPanelServer


def detect_lan_ipv4() -> str | None:
    """Best-effort detection of the PC's private IPv4 address."""

    candidates: list[str] = []

    # A UDP connect chooses the default IPv4 route without needing a successful
    # connection or sending application data.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass

    for candidate in candidates:
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if ip.version == 4 and ip.is_private and not ip.is_loopback:
            return str(ip)
    return None


class LocalRuntimeMonitor:
    """Local MT5 health monitor plus web-controlled strategy evaluator.

    The worker reads M15 candles from MT5, evaluates the selected BUY/SELL Fib
    rules and calculates the planned position size from the account owner's web
    settings. Live order submission remains disabled until the execution adapter
    is explicitly enabled and tested.
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
            "sizing_mode": settings.sizing_mode,
            "configured_execution_mode": settings.execution_mode,
            "live_execution_enabled": False,
            "mt5_connected": False,
            "account_connected": False,
            "open_positions": None,
            "position_limit_reached": False,
            "strategy_evaluating": False,
            "last_setup": None,
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
                    payload["account_currency"] = getattr(account, "currency", None)
                    payload["account_balance"] = float(getattr(account, "balance", 0.0) or 0.0)
                    payload["account_equity"] = float(getattr(account, "equity", 0.0) or 0.0)
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
                    loss_per_one_lot: float | None = None
                    if settings.sizing_mode != "fixed_lot":
                        order_type = (
                            mt5.ORDER_TYPE_BUY if setup.side == "BUY" else mt5.ORDER_TYPE_SELL
                        )
                        calculated = mt5.order_calc_profit(
                            order_type,
                            symbol,
                            1.0,
                            float(setup.entry),
                            float(setup.stop_loss),
                        )
                        if calculated is not None:
                            loss_per_one_lot = abs(float(calculated))

                    planned_size = calculate_position_size(
                        settings,
                        account_equity=float(payload.get("account_equity") or 0.0),
                        loss_per_one_lot=loss_per_one_lot,
                        volume_min=float(getattr(info, "volume_min", 0.0) or 0.0),
                        volume_max=float(getattr(info, "volume_max", 0.0) or 0.0),
                        volume_step=float(getattr(info, "volume_step", 0.0) or 0.0),
                    )

                    payload["last_setup"] = {
                        "side": setup.side,
                        "entry": setup.entry,
                        "stop_loss": setup.stop_loss,
                        "take_profit": setup.take_profit,
                        "reward_to_risk": setup.reward_to_risk,
                        "planned_volume": planned_size.volume,
                        "planned_risk_amount": planned_size.risk_amount,
                        "sizing_mode": planned_size.mode,
                        "execution_mode": settings.execution_mode,
                    }
                    payload["message"] = (
                        f"{symbol}: qualifying {setup.side} setup detected; planned volume "
                        f"{planned_size.volume:g} lot(s). Live order submission is disabled."
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


def run_local_system(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    access_mode: str = "local",
    dashboard_pin: str | None = None,
) -> None:
    root = Path(root)
    settings_path = root / "config" / "runtime_settings.json"
    status_path = root / "data" / "runtime" / "system_status.json"
    diagnostics_path = root / "data" / "runtime" / "diagnostics.json"
    lan_mode = access_mode == "lan"

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

    local_url = f"http://127.0.0.1:{port}"
    lan_ip = detect_lan_ipv4() if lan_mode else None

    print("\n================================================")
    print(" FX2Active is running")
    print("================================================")
    print(f" This PC: {local_url}")
    if lan_mode:
        if lan_ip:
            print(f" Same Wi-Fi / LAN: http://{lan_ip}:{port}")
        else:
            print(" Same Wi-Fi / LAN: private IPv4 address could not be detected.")
        print(" Username: fx2active")
        print(f" Access PIN: {dashboard_pin or 'NOT SET'}")
        print(" LAN mode accepts private-network clients only.")
        print(" If Windows Firewall asks, allow Python on PRIVATE networks only.")
        print(" Do not create router port forwarding for port 8080.")
    else:
        print(" Dashboard access: this PC only.")
    print(" Keep this window open while the bot is running.")
    print(" Press Ctrl+C to stop the local system.")
    print("================================================\n")

    threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()

    server = ControlPanelServer(
        settings_path=settings_path,
        status_path=status_path,
        diagnostics_path=diagnostics_path,
        web_root=root / "web",
        host=host,
        port=port,
        dashboard_pin=dashboard_pin if lan_mode else None,
        lan_only=lan_mode,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FX2Active...")
    finally:
        monitor.stop()
