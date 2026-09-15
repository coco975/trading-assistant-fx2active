from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .trade_executor import (
    FX2ACTIVE_COMMENT,
    FX2ACTIVE_MAGIC,
    ExecutionResult,
    ExecutionStateStore,
    setup_fingerprint,
)

ORDER_COMMAND_FILE = "order_command.txt"
ORDER_RESULT_FILE = "order_result.json"
ORDER_PROTOCOL_VERSION = 1


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _clean_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("=", "-")[:64]


def write_order_command(bridge_dir: Path, payload: dict[str, Any]) -> Path:
    lines = [
        f"protocol={ORDER_PROTOCOL_VERSION}",
        f"command_id={_clean_text(str(payload['command_id']))}",
        f"mode={_clean_text(str(payload['mode']))}",
        f"side={_clean_text(str(payload['side']))}",
        f"symbol={_clean_text(str(payload['symbol']))}",
        f"volume={float(payload['volume']):.8f}",
        f"entry={float(payload['entry']):.10f}",
        f"sl={float(payload['sl']):.10f}",
        f"tp={float(payload['tp']):.10f}",
        f"deviation={int(payload['deviation'])}",
        f"max_spread_pips={float(payload['max_spread_pips']):.4f}",
        f"allow_live={1 if payload['allow_live'] else 0}",
        f"magic={FX2ACTIVE_MAGIC}",
        f"comment={FX2ACTIVE_COMMENT}",
    ]
    target = bridge_dir / ORDER_COMMAND_FILE
    _atomic_text(target, "\n".join(lines) + "\n")
    return target


def read_order_result(bridge_dir: Path, command_id: str) -> dict[str, Any] | None:
    path = bridge_dir / ORDER_RESULT_FILE
    if not path.is_file():
        return None
    for _ in range(3):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        if isinstance(payload, dict) and str(payload.get("command_id", "")) == command_id:
            return payload
        return None
    return None


def _discard_result(bridge_dir: Path) -> None:
    try:
        (bridge_dir / ORDER_RESULT_FILE).unlink(missing_ok=True)
    except OSError:
        pass


class MacTradeExecutor:
    def __init__(self, *, state_path: str | Path) -> None:
        self.state = ExecutionStateStore(state_path)

    def _result_from_payload(
        self,
        *,
        bridge_dir: Path,
        fingerprint: str,
        payload: dict[str, Any],
    ) -> ExecutionResult:
        result = self._convert_result(fingerprint, payload)
        if result.status == "blocked":
            # The MQL bridge never reached OrderSend. Delete this transient result
            # so the same valid setup can be rechecked on a later worker cycle.
            _discard_result(bridge_dir)
            return result

        # Filled/placed/partial/rejected all crossed the broker submission boundary.
        # Persist them so a restart or worker cycle cannot submit the setup again.
        self.state.record(fingerprint, result)
        return result

    def execute(
        self,
        *,
        settings: Any,
        symbol: str,
        setup: Any,
        volume: float,
        snapshot: dict[str, Any],
        snapshot_path: Path,
        timeout_seconds: float = 5.0,
    ) -> ExecutionResult:
        fingerprint = setup_fingerprint(symbol, setup, settings.execution_mode)
        if not settings.live_execution_enabled:
            return ExecutionResult(False, "disabled", "Order execution is OFF in the dashboard.", fingerprint)
        if self.state.contains(fingerprint):
            return ExecutionResult(
                False,
                "duplicate",
                "This FX2Active setup was already submitted; duplicate order blocked.",
                fingerprint,
            )

        account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
        terminal = snapshot.get("terminal") if isinstance(snapshot.get("terminal"), dict) else {}
        if not bool(terminal.get("connected")):
            return ExecutionResult(False, "blocked", "MT5 terminal is not connected.", fingerprint)
        if not bool(terminal.get("trade_allowed")) or not bool(account.get("trade_allowed")):
            return ExecutionResult(
                False,
                "blocked",
                "MT5 Algo Trading/account trading permission is disabled.",
                fingerprint,
            )

        trade_mode = account.get("trade_mode")
        if trade_mode is None and not settings.allow_live_account:
            return ExecutionResult(
                False,
                "blocked",
                "Could not verify MT5 account type. Live-account permission is OFF.",
                fingerprint,
            )
        if int(trade_mode or 0) == 2 and not settings.allow_live_account:
            return ExecutionResult(
                False,
                "blocked",
                "This is a real/live MT5 account. Enable 'Allow real/live account' to execute.",
                fingerprint,
            )

        exposure = int(snapshot.get("fx2active_open_positions", 0) or 0) + int(
            snapshot.get("fx2active_pending_orders", 0) or 0
        )
        if exposure >= settings.max_open_positions:
            return ExecutionResult(False, "blocked", "FX2Active position/order limit reached.", fingerprint)

        symbol_info = snapshot.get("symbol") if isinstance(snapshot.get("symbol"), dict) else {}
        bid = float(symbol_info.get("bid", 0.0) or 0.0)
        ask = float(symbol_info.get("ask", 0.0) or 0.0)
        point = float(symbol_info.get("point", 0.0) or 0.0)
        digits = int(symbol_info.get("digits", 0) or 0)
        pip_size = point * 10 if digits in {3, 5} else point
        if bid <= 0 or ask <= 0 or point <= 0:
            return ExecutionResult(False, "error", "MT5 bridge returned invalid market prices.", fingerprint)
        spread_pips = (ask - bid) / pip_size
        if settings.max_spread_pips > 0 and spread_pips > settings.max_spread_pips:
            return ExecutionResult(
                False,
                "blocked",
                f"Spread {spread_pips:.1f} pips exceeds limit {settings.max_spread_pips:g}.",
                fingerprint,
            )

        bridge_dir = snapshot_path.parent
        existing = read_order_result(bridge_dir, fingerprint)
        if existing is not None:
            existing_result = self._convert_result(fingerprint, existing)
            if existing_result.status != "blocked":
                self.state.record(fingerprint, existing_result)
                return existing_result
            _discard_result(bridge_dir)

        command = {
            "command_id": fingerprint,
            "mode": "PENDING" if settings.execution_mode == "pending_limit" else "MARKET",
            "side": str(setup.side).upper(),
            "symbol": symbol,
            "volume": float(volume),
            "entry": float(setup.entry),
            "sl": float(setup.stop_loss),
            "tp": float(setup.take_profit),
            "deviation": int(settings.max_deviation_points),
            "max_spread_pips": float(settings.max_spread_pips),
            "allow_live": bool(settings.allow_live_account),
        }
        write_order_command(bridge_dir, command)

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            payload = read_order_result(bridge_dir, fingerprint)
            if payload is not None:
                return self._result_from_payload(
                    bridge_dir=bridge_dir,
                    fingerprint=fingerprint,
                    payload=payload,
                )
            time.sleep(0.1)

        ambiguous = ExecutionResult(
            False,
            "ambiguous",
            "MT5 bridge did not acknowledge the order in time. Duplicate retry blocked.",
            fingerprint,
            volume=float(volume),
        )
        self.state.record(fingerprint, ambiguous)
        return ambiguous

    @staticmethod
    def _convert_result(fingerprint: str, payload: dict[str, Any]) -> ExecutionResult:
        ok = bool(payload.get("ok"))
        retcode = int(payload.get("retcode", 0) or 0) or None
        return ExecutionResult(
            ok,
            str(payload.get("status", "filled" if ok else "rejected")),
            str(payload.get("message", "MT5 bridge returned an execution result.")),
            fingerprint,
            retcode=retcode,
            order_ticket=int(payload.get("order", 0) or 0) or None,
            deal_ticket=int(payload.get("deal", 0) or 0) or None,
            volume=float(payload.get("volume", 0.0) or 0.0) or None,
            price=float(payload.get("price", 0.0) or 0.0) or None,
        )
