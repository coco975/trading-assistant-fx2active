from __future__ import annotations

import ipaddress
import json
import platform
import socket
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .controlled_strategy import WebControlledFibStrategy
from .mac_bridge import bridge_loss_per_one_lot, load_snapshot, snapshot_is_fresh, write_requested_symbol
from .models import Candle
from .position_sizing import calculate_position_size
from .runtime_settings import RuntimeSettingsStore
from .system_diagnostics import run_diagnostics
from .web_server import ControlPanelServer


def detect_lan_ipv4() -> str | None:
    """Best-effort detection of the computer's private IPv4 address."""

    candidates: list[str] = []
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
    """MT5 health monitor plus web-controlled strategy evaluator."""

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
    def _pip_size_values(point: float, digits: int) -> float:
        if point <= 0:
            raise ValueError("MT5 returned an invalid point size for the symbol")
        return point * 10 if digits in {3, 5} else point

    @classmethod
    def _pip_size(cls, symbol_info: Any) -> float:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        digits = int(getattr(symbol_info, "digits", 0) or 0)
        return cls._pip_size_values(point, digits)

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

    @staticmethod
    def _candles_from_bridge_rates(rates: Any) -> list[Candle]:
        candles: list[Candle] = []
        if not isinstance(rates, list):
            return candles
        for row in rates:
            if not isinstance(row, list) or len(row) < 5:
                continue
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(row[0]), tz=timezone.utc),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                )
            )
        return candles

    @staticmethod
    def _mask_login(login: Any) -> str | None:
        text = str(login or "")
        if not text:
            return None
        return "*" * max(0, len(text) - 4) + text[-4:]

    def _evaluate(
        self,
        *,
        payload: dict[str, Any],
        settings: Any,
        symbol: str,
        candles: list[Candle],
        pip_size: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
        loss_calculator: Callable[[Any], float | None],
    ) -> dict[str, Any]:
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
            loss_per_one_lot = None if settings.sizing_mode == "fixed_lot" else loss_calculator(setup)
            planned_size = calculate_position_size(
                settings,
                account_equity=float(payload.get("account_equity") or 0.0),
                loss_per_one_lot=loss_per_one_lot,
                volume_min=volume_min,
                volume_max=volume_max,
                volume_step=volume_step,
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
        return payload

    def _snapshot_windows(self, payload: dict[str, Any], settings: Any) -> dict[str, Any]:
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
                payload["account_login_masked"] = self._mask_login(getattr(account, "login", None))
                payload["account_server"] = getattr(account, "server", None)
                payload["account_currency"] = getattr(account, "currency", None)
                payload["account_balance"] = float(getattr(account, "balance", 0.0) or 0.0)
                payload["account_equity"] = float(getattr(account, "equity", 0.0) or 0.0)
                payload["trade_allowed"] = bool(getattr(account, "trade_allowed", True))

            positions = mt5.positions_get()
            payload["open_positions"] = len(positions) if positions is not None else 0
            payload["position_limit_reached"] = payload["open_positions"] >= settings.max_open_positions

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

            candles = self._candles_from_rates(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 300))
            pip_size = self._pip_size(info)

            def loss_calculator(setup: Any) -> float | None:
                order_type = mt5.ORDER_TYPE_BUY if setup.side == "BUY" else mt5.ORDER_TYPE_SELL
                calculated = mt5.order_calc_profit(
                    order_type,
                    symbol,
                    1.0,
                    float(setup.entry),
                    float(setup.stop_loss),
                )
                return abs(float(calculated)) if calculated is not None else None

            return self._evaluate(
                payload=payload,
                settings=settings,
                symbol=symbol,
                candles=candles,
                pip_size=pip_size,
                volume_min=float(getattr(info, "volume_min", 0.0) or 0.0),
                volume_max=float(getattr(info, "volume_max", 0.0) or 0.0),
                volume_step=float(getattr(info, "volume_step", 0.0) or 0.0),
                loss_calculator=loss_calculator,
            )
        finally:
            mt5.shutdown()

    def _snapshot_macos(self, payload: dict[str, Any], settings: Any) -> dict[str, Any]:
        if settings.symbol:
            write_requested_symbol(settings.symbol)

        snapshot, snapshot_path = load_snapshot()
        payload["mt5_bridge"] = str(snapshot_path)
        if not snapshot_is_fresh(snapshot):
            payload["message"] = "The macOS MT5 bridge is not updating. Keep MetaTrader 5 open with FX2ActiveBridge attached."
            return payload

        terminal = snapshot.get("terminal") if isinstance(snapshot.get("terminal"), dict) else {}
        account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
        payload["mt5_connected"] = bool(terminal.get("connected"))
        payload["account_connected"] = bool(account.get("login"))
        payload["account_login_masked"] = self._mask_login(account.get("login"))
        payload["account_server"] = account.get("server")
        payload["account_currency"] = account.get("currency")
        payload["account_balance"] = float(account.get("balance", 0.0) or 0.0)
        payload["account_equity"] = float(account.get("equity", 0.0) or 0.0)
        payload["trade_allowed"] = bool(account.get("trade_allowed")) and bool(terminal.get("trade_allowed"))
        payload["open_positions"] = int(snapshot.get("open_positions", 0) or 0)
        payload["position_limit_reached"] = payload["open_positions"] >= settings.max_open_positions

        if not payload["mt5_connected"] or not payload["account_connected"]:
            payload["message"] = "MT5 is not fully connected/logged in."
            return payload
        if not settings.symbol:
            payload["message"] = "MT5 is online. Set the Trading Symbol on the dashboard."
            return payload

        symbol_info = snapshot.get("symbol") if isinstance(snapshot.get("symbol"), dict) else {}
        bridge_symbol = str(symbol_info.get("name", ""))
        if bridge_symbol != settings.symbol:
            payload["message"] = f"Waiting for the MT5 bridge to switch to {settings.symbol}."
            return payload
        if not bool(symbol_info.get("selected")):
            payload["message"] = f"MT5 symbol '{settings.symbol}' was not found or could not be selected."
            return payload

        point = float(symbol_info.get("point", 0.0) or 0.0)
        digits = int(symbol_info.get("digits", 0) or 0)
        pip_size = self._pip_size_values(point, digits)
        candles = self._candles_from_bridge_rates(snapshot.get("rates"))

        def loss_calculator(setup: Any) -> float | None:
            return bridge_loss_per_one_lot(symbol_info, float(setup.entry), float(setup.stop_loss))

        return self._evaluate(
            payload=payload,
            settings=settings,
            symbol=settings.symbol,
            candles=candles,
            pip_size=pip_size,
            volume_min=float(symbol_info.get("volume_min", 0.0) or 0.0),
            volume_max=float(symbol_info.get("volume_max", 0.0) or 0.0),
            volume_step=float(symbol_info.get("volume_step", 0.0) or 0.0),
            loss_calculator=loss_calculator,
        )

    def _snapshot(self) -> dict[str, Any]:
        settings = self.store.load()
        payload: dict[str, Any] = {
            "worker_online": True,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "runtime_platform": platform.system(),
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
            system = platform.system()
            if system == "Windows":
                return self._snapshot_windows(payload, settings)
            if system == "Darwin":
                return self._snapshot_macos(payload, settings)
            payload["message"] = f"FX2Active runtime is not supported on {system}."
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
    device_label = "This Mac" if platform.system() == "Darwin" else "This PC"

    print("\n================================================")
    print(" FX2Active is running")
    print("================================================")
    print(f" {device_label}: {local_url}")
    if lan_mode:
        if lan_ip:
            print(f" Same Wi-Fi / LAN: http://{lan_ip}:{port}")
        else:
            print(" Same Wi-Fi / LAN: private IPv4 address could not be detected.")
        print(f" Access PIN: {dashboard_pin or 'NOT SET'}")
        print(" Enter the PIN once; the browser keeps a session cookie until that browser session ends.")
        print(" LAN mode accepts private-network clients only.")
        if platform.system() == "Windows":
            print(" If Windows Firewall asks, allow Python on PRIVATE networks only.")
        else:
            print(" If macOS asks about incoming connections, allow them for this local Python process.")
        print(" Do not create router port forwarding for port 8080.")
    else:
        print(" Dashboard access: this computer only.")
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
