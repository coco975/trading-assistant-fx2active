from __future__ import annotations

import importlib.util
import json
import math
import platform
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .mac_bridge import (
    BRIDGE_PROTOCOL_VERSION,
    bridge_source_needs_compile,
    find_installed_bridge_sources,
    load_snapshot,
    snapshot_age_seconds,
    snapshot_is_fresh,
)
from .runtime_settings import RuntimeSettingsStore


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool
    message: str
    level: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _check_port(host: str, port: int) -> DiagnosticCheck:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return DiagnosticCheck("Local web port", True, f"{host}:{port} is available")
    except OSError as exc:
        return DiagnosticCheck("Local web port", False, f"{host}:{port} is already in use ({exc})")
    finally:
        sock.close()


def _mask_login(login: Any) -> str | None:
    if login is None:
        return None
    text = str(login)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def _windows_mt5_checks(checks: list[DiagnosticCheck], details: dict[str, Any]) -> None:
    architecture_ok = sys.maxsize > 2**32
    checks.append(
        DiagnosticCheck(
            "Python architecture",
            architecture_ok,
            "64-bit Python" if architecture_ok else "64-bit Python is required for MetaTrader5",
        )
    )
    if not architecture_ok:
        return

    mt5_spec = importlib.util.find_spec("MetaTrader5")
    if mt5_spec is None:
        checks.append(
            DiagnosticCheck(
                "MetaTrader5 Python bridge",
                False,
                "Python package MetaTrader5 is not installed",
            )
        )
        return

    checks.append(DiagnosticCheck("MetaTrader5 Python bridge", True, "Python bridge is installed"))
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            checks.append(
                DiagnosticCheck(
                    "MT5 terminal",
                    False,
                    f"Could not connect to an installed/running MT5 terminal. MT5 error: {mt5.last_error()}",
                )
            )
            return

        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            connected = bool(getattr(terminal, "connected", False)) if terminal else False
            checks.append(
                DiagnosticCheck(
                    "MT5 terminal",
                    connected,
                    "MT5 terminal is connected" if connected else "MT5 terminal is open but not connected",
                )
            )

            terminal_trade_allowed = bool(getattr(terminal, "trade_allowed", False)) if terminal else False
            trade_api_disabled = bool(getattr(terminal, "tradeapi_disabled", True)) if terminal else True
            permission_ok = terminal_trade_allowed and not trade_api_disabled
            if permission_ok:
                permission_message = "MT5 AutoTrading/Python trading access is enabled"
            elif trade_api_disabled:
                permission_message = "MT5 is blocking trading through the external Python API"
            else:
                permission_message = "MT5 AutoTrading is currently disabled"
            checks.append(
                DiagnosticCheck(
                    "AutoTrading / API permission",
                    permission_ok,
                    permission_message,
                )
            )

            if account is None:
                checks.append(DiagnosticCheck("MT5 account", False, "No logged-in MT5 trading account was detected"))
            else:
                server = getattr(account, "server", None)
                login = getattr(account, "login", None)
                checks.append(
                    DiagnosticCheck(
                        "MT5 account",
                        True,
                        f"Logged in on {server or 'unknown server'} as {_mask_login(login) or 'account'}",
                    )
                )
                details["mt5"] = {
                    "connection": "python",
                    "connected": connected,
                    "server": server,
                    "login_masked": _mask_login(login),
                    "trade_allowed": terminal_trade_allowed,
                    "trade_api_disabled": trade_api_disabled,
                }
        finally:
            mt5.shutdown()
    except Exception as exc:
        checks.append(DiagnosticCheck("MT5 diagnostic", False, f"MT5 check failed: {exc}"))


def _macos_mt5_checks(checks: list[DiagnosticCheck], details: dict[str, Any]) -> None:
    sources = find_installed_bridge_sources()
    if sources:
        needs_compile = all(bridge_source_needs_compile(source) for source in sources)
        checks.append(
            DiagnosticCheck(
                "FX2Active bridge program",
                not needs_compile,
                (
                    "Latest FX2ActiveBridge source and compiled EA were detected"
                    if not needs_compile
                    else "Latest bridge source is installed but FX2ActiveBridge.ex5 is missing or older; compile it once in MetaEditor"
                ),
                level="warning" if needs_compile else "error",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "FX2Active bridge program",
                False,
                "FX2ActiveBridge.mq5 is not installed in a detected MT5 MQL5/Experts folder",
                level="warning",
            )
        )

    try:
        snapshot, path = load_snapshot()
    except Exception as exc:
        checks.append(
            DiagnosticCheck(
                "FX2Active MT5 bridge",
                False,
                f"{exc} Keep MT5 open, compile/attach FX2ActiveBridge, then run the check again.",
            )
        )
        return

    fresh = snapshot_is_fresh(snapshot)
    age = snapshot_age_seconds(snapshot)
    if fresh:
        bridge_message = f"Bridge protocol {BRIDGE_PROTOCOL_VERSION} is updating ({age:.1f}s old)"
    elif math.isfinite(age):
        bridge_message = f"Bridge snapshot is stale ({age:.1f}s old)"
    else:
        bridge_message = "Bridge heartbeat is invalid, out of date, or the Mac clock is not synchronized"
    checks.append(DiagnosticCheck("FX2Active MT5 bridge", fresh, bridge_message))

    terminal = snapshot.get("terminal") if isinstance(snapshot.get("terminal"), dict) else {}
    account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
    connected = bool(terminal.get("connected"))
    checks.append(
        DiagnosticCheck(
            "MT5 terminal",
            connected,
            "MT5 terminal is connected" if connected else "MT5 terminal is open but not connected",
        )
    )

    permission_ok = bool(terminal.get("trade_allowed")) and bool(account.get("trade_allowed"))
    checks.append(
        DiagnosticCheck(
            "AutoTrading permission",
            permission_ok,
            "MT5 Algo Trading is enabled" if permission_ok else "Enable Algo Trading in MT5",
        )
    )

    login = account.get("login")
    if not login:
        checks.append(DiagnosticCheck("MT5 account", False, "No logged-in MT5 trading account was detected"))
    else:
        server = account.get("server")
        checks.append(
            DiagnosticCheck(
                "MT5 account",
                True,
                f"Logged in on {server or 'unknown server'} as {_mask_login(login) or 'account'}",
            )
        )
        details["mt5"] = {
            "connection": "mac_file_bridge",
            "bridge_path": str(path),
            "bridge_protocol": snapshot.get("protocol_version"),
            "bridge_version": snapshot.get("bridge_version"),
            "terminal_build": terminal.get("build"),
            "connected": connected,
            "server": server,
            "login_masked": _mask_login(login),
            "trade_allowed": permission_ok,
        }


def run_diagnostics(
    *,
    settings_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    include_port_check: bool = True,
) -> dict[str, Any]:
    checks: list[DiagnosticCheck] = []
    details: dict[str, Any] = {}

    python_ok = sys.version_info >= (3, 11)
    checks.append(
        DiagnosticCheck(
            "Python",
            python_ok,
            f"Python {platform.python_version()}" if python_ok else "Python 3.11+ is required",
        )
    )

    system = platform.system()
    os_ok = system in {"Windows", "Darwin"}
    os_message = platform.platform() if os_ok else "FX2Active supports Windows and macOS"
    checks.append(DiagnosticCheck("Operating system", os_ok, os_message))
    details["platform"] = system

    try:
        settings = RuntimeSettingsStore(settings_path).load()
        checks.append(DiagnosticCheck("Strategy settings", True, "Runtime settings loaded and validated"))
        details["settings"] = {
            "trading_enabled": settings.trading_enabled,
            "allow_buys": settings.allow_buys,
            "allow_sells": settings.allow_sells,
            "symbol": settings.symbol,
            "max_open_positions": settings.max_open_positions,
            "timeframe": settings.timeframe,
        }
    except Exception as exc:
        checks.append(DiagnosticCheck("Strategy settings", False, str(exc)))

    if include_port_check:
        checks.append(_check_port(host, port))

    if system == "Windows":
        _windows_mt5_checks(checks, details)
    elif system == "Darwin":
        _macos_mt5_checks(checks, details)

    ready = all(check.ok or check.level == "warning" for check in checks)
    return {
        "ready": ready,
        "checks": [check.to_dict() for check in checks],
        "details": details,
    }


def save_report(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
