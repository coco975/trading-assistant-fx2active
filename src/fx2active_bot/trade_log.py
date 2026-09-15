from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeLogStore:
    """Small local event log for setup and execution history."""

    def __init__(self, path: str | Path, *, max_entries: int = 250) -> None:
        self.path = Path(path)
        self.max_entries = max_entries

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("FX2Active trade log is unreadable") from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise RuntimeError("FX2Active trade log has an invalid format")
        return payload

    def read(self, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), self.max_entries))
        items = self._load()
        return list(reversed(items[-limit:]))

    def append(self, event: dict[str, Any], *, event_key: str) -> bool:
        items = self._load()
        if any(str(item.get("event_key", "")) == event_key for item in items):
            return False

        record = dict(event)
        record["event_key"] = event_key
        record.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        items.append(record)
        if len(items) > self.max_entries:
            items = items[-self.max_entries :]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items, handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return True
