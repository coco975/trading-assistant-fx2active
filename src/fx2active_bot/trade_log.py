from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeLogStore:
    """Persistent local history of detected setups and execution results."""

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

    def _append_unlocked(self, items: list[dict[str, Any]], event: dict[str, Any]) -> bool:
        event_key = str(event.get("event_key", ""))
        if event_key and any(str(item.get("event_key", "")) == event_key for item in items):
            return False
        record = dict(event)
        record.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        items.append(record)
        self._save_unlocked(items)
        return True

    def capture_status(self, status: dict[str, Any]) -> None:
        """Record new setup/execution events from the runtime status payload."""

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

        pending: list[dict[str, Any]] = []
        if setup:
            setup_key = "|".join(
                (
                    "setup",
                    symbol,
                    str(setup.get("side") or ""),
                    str(setup.get("swing_high") or ""),
                    str(setup.get("swing_low") or ""),
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
                        "price": execution.get("price") if execution.get("price") is not None else (setup.get("entry") if setup else None),
                        "volume": execution.get("volume") if execution.get("volume") is not None else (setup.get("planned_volume") if setup else None),
                        "status": execution.get("status") or "Result",
                        "message": execution.get("message"),
                        "retcode": execution.get("retcode"),
                        "order_ticket": execution.get("order_ticket"),
                        "deal_ticket": execution.get("deal_ticket"),
                    }
                )

        if not pending:
            return
        with self._lock:
            items = self._load_unlocked()
            changed = False
            for event in pending:
                event_key = str(event.get("event_key", ""))
                if event_key and any(str(item.get("event_key", "")) == event_key for item in items):
                    continue
                record = dict(event)
                record.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
                items.append(record)
                changed = True
            if changed:
                self._save_unlocked(items)
