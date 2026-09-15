from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeLogStore:
    """Persistent local history of detected setups, execution and closed trades."""

    def __init__(self, path: str | Path, *, max_entries: int = 250) -> None:
        self.path = Path(path)
        self.max_entries = max_entries
        self._lock = threading.Lock()

    def _load_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("FX2Active trade log is unreadable") from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise RuntimeError("FX2Active trade log has an invalid format")
        return payload

    def _save_unlocked(self, items: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items[-self.max_entries :], handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def read(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), self.max_entries))
        with self._lock:
            items = self._load_unlocked()
        return list(reversed(items[-limit:]))

    def clear(self) -> None:
        with self._lock:
            self._save_unlocked([])

    @staticmethod
    def _profit_status(value: Any) -> str:
        try:
            net = float(value)
        except (TypeError, ValueError):
            return "Closed"
        if net > 1e-9:
            return "Profit"
        if net < -1e-9:
            return "Loss"
        return "Breakeven"

    def capture_status(self, status: dict[str, Any]) -> None:
        """Record new setup, execution and broker-close events from runtime status."""

        if not isinstance(status, dict):
            return
        timestamp = str(status.get("heartbeat_at") or datetime.now(timezone.utc).isoformat())
        symbol = str(status.get("symbol") or "")
        setup = status.get("last_setup") if isinstance(status.get("last_setup"), dict) else None
        execution = (
            status.get("execution_result")
            if isinstance(status.get("execution_result"), dict)
            else None
        )
        closed_trades = status.get("closed_trades")
        if not isinstance(closed_trades, list):
            closed_trades = []

        pending: list[dict[str, Any]] = []
        if setup:
            setup_key = "|".join(
                (
                    "setup",
                    symbol,
                    str(setup.get("side") or ""),
                    str(setup.get("swing_high") or ""),
                    str(setup.get("swing_low") or ""),
                    str(setup.get("swing_high_time") or ""),
                    str(setup.get("swing_low_time") or ""),
                    str(setup.get("entry") or ""),
                )
            )
            pending.append(
                {
                    "event_key": setup_key,
                    "timestamp_utc": timestamp,
                    "event": "Setup",
                    "symbol": symbol,
                    "side": setup.get("side"),
                    "price": setup.get("entry"),
                    "volume": setup.get("planned_volume"),
                    "status": "Detected",
                    "swing_high": setup.get("swing_high"),
                    "swing_low": setup.get("swing_low"),
                    "stop_loss": setup.get("stop_loss"),
                    "take_profit": setup.get("take_profit"),
                }
            )

        if execution:
            status_name = str(execution.get("status") or "").lower()
            if status_name not in {"disabled", "duplicate"}:
                execution_key = "|".join(
                    (
                        "execution",
                        str(execution.get("fingerprint") or ""),
                        status_name,
                        str(execution.get("order_ticket") or ""),
                        str(execution.get("deal_ticket") or ""),
                        str(execution.get("retcode") or ""),
                    )
                )
                pending.append(
                    {
                        "event_key": execution_key,
                        "timestamp_utc": timestamp,
                        "event": "Execution",
                        "symbol": symbol,
                        "side": setup.get("side") if setup else None,
                        "price": execution.get("price")
                        if execution.get("price") is not None
                        else (setup.get("entry") if setup else None),
                        "volume": execution.get("volume")
                        if execution.get("volume") is not None
                        else (setup.get("planned_volume") if setup else None),
                        "status": execution.get("status") or "Result",
                        "message": execution.get("message"),
                        "retcode": execution.get("retcode"),
                        "order_ticket": execution.get("order_ticket"),
                        "deal_ticket": execution.get("deal_ticket"),
                    }
                )

        for closed in closed_trades:
            if not isinstance(closed, dict):
                continue
            deal_ticket = closed.get("deal_ticket")
            position_id = closed.get("position_id")
            closed_at = closed.get("timestamp_utc") or timestamp
            key_suffix = deal_ticket or f"{position_id}|{closed_at}|{closed.get('price')}"
            net_profit = closed.get("net_profit")
            pending.append(
                {
                    "event_key": f"closed|{key_suffix}",
                    "timestamp_utc": str(closed_at),
                    "event": "Closed",
                    "symbol": closed.get("symbol") or symbol,
                    "side": closed.get("side"),
                    "price": closed.get("price"),
                    "volume": closed.get("volume"),
                    "status": self._profit_status(net_profit),
                    "profit": closed.get("profit"),
                    "commission": closed.get("commission"),
                    "swap": closed.get("swap"),
                    "fee": closed.get("fee"),
                    "net_profit": net_profit,
                    "close_reason": closed.get("close_reason"),
                    "deal_ticket": deal_ticket,
                    "position_id": position_id,
                }
            )

        if not pending:
            return
        with self._lock:
            items = self._load_unlocked()
            existing_keys = {str(item.get("event_key", "")) for item in items}
            changed = False
            for event in pending:
                event_key = str(event.get("event_key", ""))
                if event_key and event_key in existing_keys:
                    continue
                record = dict(event)
                record.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
                items.append(record)
                if event_key:
                    existing_keys.add(event_key)
                changed = True
            if changed:
                self._save_unlocked(items)
