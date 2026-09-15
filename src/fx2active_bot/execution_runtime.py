from __future__ import annotations

import json
import platform
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable

from .controlled_strategy import WebControlledFibStrategy
from .local_runtime import LocalRuntimeMonitor, detect_lan_ipv4
from .mac_bridge import bridge_loss_per_one_lot, load_snapshot, snapshot_is_fresh, write_requested_symbol
from .mac_trade_executor import MacTradeExecutor
from .position_sizing import calculate_position_size
from .runtime_settings import RuntimeSettingsStore
from .system_diagnostics import run_diagnostics
from .trade_executor import WindowsTradeExecutor, count_bot_exposure
from .web_server import ControlPanelServer


class ExecutionRuntimeMonitor(LocalRuntimeMonitor):
    """FX2Active runtime with guarded Windows and macOS MT5 order execution."""

    def __init__(self, *, root: str | Path, settings_path: str | Path, status_path: str | Path) -> None:
        super().__init__(settings_path=settings_path, status_path=status_path)
        state_path = Path(root) / "data" / "runtime" / "execution_state.json"
        self.windows_executor = WindowsTradeExecutor(state_path=state_path)
        self.mac_executor = MacTradeExecutor(state_path=state_path)
        self.execution_context: dict[str, Any] = {}

    def _evaluate(
        self,
        *,
        payload: dict[str, Any],
        settings: Any,
        symbol: str,
        candles: list[Any],
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
            current_open_positions=int(payload.get("bot_exposure", 0) or 0),
        )
        if setup is None:
            if not settings.trading_enabled:
                payload["message"] = f"{symbol}: strategy worker online; trading is disabled."
            elif payload.get("position_limit_reached"):
                payload["message"] = f"{symbol}: FX2Active position/order limit reached."
            else:
                payload["message"] = f"{symbol}: strategy worker online; no qualifying setup right now."
            return payload

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
            "swing_low": setup.swing_low,
            "swing_high": setup.swing_high,
            "reward_to_risk": setup.reward_to_risk,
            "planned_volume": planned_size.volume,
            "planned_risk_amount": planned_size.risk_amount,
            "sizing_mode": planned_size.mode,
            "execution_mode": settings.execution_mode,
        }

        if not settings.live_execution_enabled:
            payload["message"] = (
                f"{symbol}: qualifying {setup.side} setup detected; planned volume "
                f"{planned_size.volume:g} lot(s). Order execution is OFF."
            )
            return payload

        system = self.execution_context.get("platform")
        if system == "Windows":
            result = self.windows_executor.execute(
                mt5=self.execution_context["mt5"],
                settings=settings,
                symbol=symbol,
                setup=setup,
                volume=planned_size.volume,
                pip_size=pip_size,
                account=self.execution_context["account"],
                symbol_info=self.execution_context["symbol_info"],
            )
        elif system == "Darwin":
            snapshot = self.execution_context["snapshot"]
            if not bool(snapshot.get("execution_bridge")):
                payload["message"] = (
                    "The attached macOS FX2ActiveBridge is read-only/outdated. "
                    "Compile the latest bridge before enabling order execution."
                )
                payload["execution_result"] = {
                    "ok": False,
                    "status": "blocked",
                    "message": payload["message"],
                }
                return payload
            result = self.mac_executor.execute(
                settings=settings,
                symbol=symbol,
                setup=setup,
                volume=planned_size.volume,
                snapshot=snapshot,
                snapshot_path=self.execution_context["snapshot_path"],
            )
        else:
            payload["message"] = "Trade execution is not supported on this operating system."
            return payload

        payload["execution_result"] = result.to_dict()
        payload["message"] = f"{symbol}: {result.message}"
        return payload

    @staticmethod
    def _count_all_magic(mt5: Any) -> tuple[int, int]:
        from .trade_executor import FX2ACTIVE_MAGIC

        positions = mt5.positions_get()
        orders = mt5.orders_get()
        pos = sum(1 for item in positions or () if int(getattr(item, "magic", 0) or 0) == FX2ACTIVE_MAGIC)
        pending = sum(1 for item in orders or () if int(getattr(item, "magic", 0) or 0) == FX2ACTIVE_MAGIC)
        return pos, pending

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
                payload["trade_allowed"] = bool(getattr(account, "trade_allowed", False))
                payload["account_trade_mode"] = getattr(account, "trade_mode", None)

            all_positions = mt5.positions_get()
            payload["account_total_open_positions"] = len(all_positions) if all_positions is not None else 0

            if settings.symbol:
                bot_positions, bot_pending = count_bot_exposure(mt5, settings.symbol)
            else:
                bot_positions, bot_pending = self._count_all_magic(mt5)
            payload["open_positions"] = bot_positions
            payload["pending_orders"] = bot_pending
            payload["bot_exposure"] = bot_positions + bot_pending
            payload["position_limit_reached"] = payload["bot_exposure"] >= settings.max_open_positions

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

            self.execution_context = {
                "platform": "Windows",
                "mt5": mt5,
                "account": account,
                "symbol_info": info,
            }
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
            self.execution_context = {}
            mt5.shutdown()

    def _snapshot_macos(self, payload: dict[str, Any], settings: Any) -> dict[str, Any]:
        if settings.symbol:
            write_requested_symbol(settings.symbol)

        snapshot, snapshot_path = load_snapshot()
        payload["mt5_bridge"] = str(snapshot_path)
        if not snapshot_is_fresh(snapshot):
            payload["message"] = "The macOS MT5 bridge is not updating. Keep FX2ActiveBridge attached."
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
        payload["account_trade_mode"] = account.get("trade_mode")
        payload["trade_allowed"] = bool(account.get("trade_allowed")) and bool(terminal.get("trade_allowed"))
        payload["account_total_open_positions"] = int(snapshot.get("open_positions", 0) or 0)
        payload["open_positions"] = int(snapshot.get("fx2active_open_positions", 0) or 0)
        payload["pending_orders"] = int(snapshot.get("fx2active_pending_orders", 0) or 0)
        payload["bot_exposure"] = payload["open_positions"] + payload["pending_orders"]
        payload["position_limit_reached"] = payload["bot_exposure"] >= settings.max_open_positions

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

        self.execution_context = {
            "platform": "Darwin",
            "snapshot": snapshot,
            "snapshot_path": snapshot_path,
        }
        try:
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
        finally:
            self.execution_context = {}

    def _snapshot(self) -> dict[str, Any]:
        settings = self.store.load()
        payload: dict[str, Any] = {
            "worker_online": True,
            "runtime_platform": platform.system(),
            "trading_enabled": settings.trading_enabled,
            "live_execution_enabled": settings.live_execution_enabled,
            "allow_live_account": settings.allow_live_account,
            "allow_buys": settings.allow_buys,
            "allow_sells": settings.allow_sells,
            "symbol": settings.symbol,
            "max_open_positions": settings.max_open_positions,
            "sizing_mode": settings.sizing_mode,
            "configured_execution_mode": settings.execution_mode,
            "mt5_connected": False,
            "account_connected": False,
            "open_positions": None,
            "pending_orders": None,
            "position_limit_reached": False,
            "strategy_evaluating": False,
            "last_setup": None,
            "execution_result": None,
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
            payload["message"] = f"Worker health/strategy/execution check failed: {exc}"
        return payload


def run_execution_system(
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

    monitor = ExecutionRuntimeMonitor(root=root, settings_path=settings_path, status_path=status_path)
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
    print(" Broker execution is controlled separately from the strategy master switch.")
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
