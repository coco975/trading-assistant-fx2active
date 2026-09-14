from __future__ import annotations

import json
import os
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

BRIDGE_DIR_NAME = "FX2Active"
SNAPSHOT_FILE = "snapshot.json"
REQUESTED_SYMBOL_FILE = "requested_symbol.txt"
BRIDGE_STALE_SECONDS = 15.0


def _candidate_prefixes() -> list[Path]:
    home = Path.home()
    app_support = home / "Library" / "Application Support"
    return [
        app_support / "net.metaquotes.wine.metatrader5",
        app_support / "MetaTrader 5",
        app_support / "Metatrader 5",
    ]


def _search_roots() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Library" / "Application Support",
        home / "Library" / "Containers",
        home / ".wine",
    ]
    return [path for path in candidates if path.is_dir()]


def _bounded_dirs(root: Path, *, max_depth: int = 3) -> Iterator[Path]:
    """Yield directories under root without recursively walking the whole Mac.

    Broker-branded MT5 installations can use their own Application Support
    folder. We only need to discover Wine prefixes, so a shallow scan is much
    faster and avoids walking caches, browser data and unrelated containers.
    """

    root_depth = len(root.parts)
    stack = [root]
    seen: set[Path] = set()

    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        yield current

        depth = len(current.parts) - root_depth
        if depth >= max_depth:
            continue

        try:
            children = list(current.iterdir())
        except (OSError, PermissionError):
            continue

        for child in children:
            try:
                if child.is_dir() and not child.is_symlink():
                    stack.append(child)
            except (OSError, PermissionError):
                continue


@lru_cache(maxsize=1)
def _wine_prefixes() -> tuple[Path, ...]:
    """Find standard and broker-branded Wine prefixes quickly."""

    found: list[Path] = []

    for prefix in _candidate_prefixes():
        if prefix.is_dir() and prefix not in found:
            found.append(prefix)

    for root in _search_roots():
        # ~/.wine is itself normally the prefix.
        if (root / "drive_c").is_dir() and root not in found:
            found.append(root)

        for candidate in _bounded_dirs(root, max_depth=3):
            try:
                if (candidate / "drive_c").is_dir() and candidate not in found:
                    found.append(candidate)
            except (OSError, PermissionError):
                continue

    return tuple(found)


def _discover_dirs(patterns: list[str]) -> list[Path]:
    found: list[Path] = []

    for prefix in _wine_prefixes():
        for pattern in patterns:
            try:
                matches = prefix.glob(pattern)
                for path in matches:
                    if path.is_dir() and path not in found:
                        found.append(path)
            except (OSError, PermissionError):
                continue

    return found


def find_common_files_dirs() -> list[Path]:
    """Locate MetaTrader's FILE_COMMON directory inside a macOS Wine prefix."""

    override = os.environ.get("FX2ACTIVE_MT5_BRIDGE_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        return [path.parent if path.name == BRIDGE_DIR_NAME else path]

    patterns = [
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/Common/Files",
        "drive_c/users/*/Application Data/MetaQuotes/Terminal/Common/Files",
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/Common/Files/",
    ]
    return _discover_dirs(patterns)


def find_experts_dirs() -> list[Path]:
    """Locate installed MT5 MQL5/Experts directories inside macOS/Wine data."""

    patterns = [
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/*/MQL5/Experts",
        "drive_c/users/*/Application Data/MetaQuotes/Terminal/*/MQL5/Experts",
    ]
    return [path for path in _discover_dirs(patterns) if "Common" not in path.parts]


def install_bridge_source(source: str | Path) -> list[Path]:
    """Copy the bridge source into every detected MT5 Experts directory."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Bridge source does not exist: {source_path}")

    installed: list[Path] = []
    for experts_dir in find_experts_dirs():
        try:
            target_dir = experts_dir / BRIDGE_DIR_NAME
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source_path.name
            shutil.copy2(source_path, target)
            installed.append(target)
        except OSError:
            continue
    return installed


def find_snapshot_path() -> Path | None:
    candidates: list[Path] = []
    override = os.environ.get("FX2ACTIVE_MT5_BRIDGE_DIR", "").strip()
    if override:
        base = Path(override).expanduser()
        if base.name == BRIDGE_DIR_NAME:
            candidates.append(base / SNAPSHOT_FILE)
        else:
            candidates.append(base / BRIDGE_DIR_NAME / SNAPSHOT_FILE)

    for common_dir in find_common_files_dirs():
        candidates.append(common_dir / BRIDGE_DIR_NAME / SNAPSHOT_FILE)

    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def load_snapshot() -> tuple[dict[str, Any], Path]:
    path = find_snapshot_path()
    if path is None:
        raise FileNotFoundError(
            "FX2Active MT5 bridge snapshot was not found. Attach FX2ActiveBridge to a chart in MetaTrader 5."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read the FX2Active MT5 bridge snapshot: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("FX2Active MT5 bridge snapshot has an invalid format")
    return payload, path


def snapshot_age_seconds(snapshot: dict[str, Any]) -> float:
    heartbeat = float(snapshot.get("heartbeat", 0.0) or 0.0)
    if heartbeat <= 0:
        return float("inf")
    return max(0.0, time.time() - heartbeat)


def snapshot_is_fresh(snapshot: dict[str, Any]) -> bool:
    return snapshot_age_seconds(snapshot) <= BRIDGE_STALE_SECONDS


def write_requested_symbol(symbol: str) -> Path | None:
    symbol = symbol.strip()
    if not symbol:
        return None

    snapshot_path = find_snapshot_path()
    if snapshot_path is not None:
        bridge_dir = snapshot_path.parent
        bridge_dir.mkdir(parents=True, exist_ok=True)
        target = bridge_dir / REQUESTED_SYMBOL_FILE
        target.write_text(symbol + "\n", encoding="utf-8")
        return target

    for common_dir in find_common_files_dirs():
        try:
            bridge_dir = common_dir / BRIDGE_DIR_NAME
            bridge_dir.mkdir(parents=True, exist_ok=True)
            target = bridge_dir / REQUESTED_SYMBOL_FILE
            target.write_text(symbol + "\n", encoding="utf-8")
            return target
        except OSError:
            continue
    return None


def bridge_loss_per_one_lot(symbol: dict[str, Any], entry: float, stop_loss: float) -> float | None:
    tick_size = float(symbol.get("trade_tick_size", 0.0) or 0.0)
    tick_value_loss = abs(float(symbol.get("trade_tick_value_loss", 0.0) or 0.0))
    distance = abs(float(entry) - float(stop_loss))
    if tick_size <= 0 or tick_value_loss <= 0 or distance <= 0:
        return None
    return distance / tick_size * tick_value_loss
