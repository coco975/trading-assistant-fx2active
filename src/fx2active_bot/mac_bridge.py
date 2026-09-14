from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

BRIDGE_DIR_NAME = "FX2Active"
SNAPSHOT_FILE = "snapshot.json"
REQUESTED_SYMBOL_FILE = "requested_symbol.txt"
BRIDGE_STALE_SECONDS = 15.0
PREFIX_CACHE_SECONDS = 10.0

_prefix_cache: tuple[float, tuple[Path, ...]] | None = None


def _candidate_prefixes() -> list[Path]:
    home = Path.home()
    app_support = home / "Library" / "Application Support"
    return [
        app_support / "net.metaquotes.wine.metatrader5",
        app_support / "MetaTrader 5",
        app_support / "Metatrader 5",
        app_support / "MetaTrader5",
    ]


def _bounded_dirs(root: Path, *, max_depth: int = 4) -> Iterator[Path]:
    """Yield directories below root without walking an entire user profile."""

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


def _looks_like_mt5_name(name: str) -> bool:
    text = name.lower().replace(" ", "")
    return any(
        token in text
        for token in (
            "metatrader",
            "metaquotes",
            "mt5",
            "exness",
            "wine",
        )
    )


def _path_prefix_from_drive_c(path_text: str) -> Path | None:
    normalized = path_text.strip().strip('"').replace("\\ ", " ")
    marker = "/drive_c/"
    index = normalized.find(marker)
    if index <= 0:
        return None
    prefix = Path(normalized[:index]).expanduser()
    return prefix if prefix.is_dir() else None


def _prefixes_from_command(command: str) -> list[Path]:
    found: list[Path] = []
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    for part in parts:
        prefix = _path_prefix_from_drive_c(part)
        if prefix is not None and prefix not in found:
            found.append(prefix)

        if part.startswith("WINEPREFIX="):
            value = part.split("=", 1)[1].strip().strip('"').strip("'")
            candidate = Path(value).expanduser()
            if candidate.is_dir() and (candidate / "drive_c").is_dir() and candidate not in found:
                found.append(candidate)
    return found


def _running_mt5_prefixes() -> list[Path]:
    """Infer the active Wine prefix from a running MT5/Exness process."""

    found: list[Path] = []
    pids: list[str] = []
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return found

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pieces = line.split(None, 1)
        if len(pieces) != 2:
            continue
        pid, command = pieces
        lower = command.lower()
        if not any(
            token in lower
            for token in ("terminal64.exe", "metaeditor64.exe", "metatrader", "exness")
        ):
            continue

        if pid.isdigit() and pid not in pids:
            pids.append(pid)
        for prefix in _prefixes_from_command(command):
            if prefix not in found:
                found.append(prefix)

    # Wine command lines are not always descriptive. lsof normally exposes at
    # least one file underneath the active prefix, which lets us recover it.
    for pid in pids[:8]:
        try:
            opened = subprocess.run(
                ["lsof", "-Fn", "-p", pid],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        for line in opened.stdout.splitlines():
            if not line.startswith("n"):
                continue
            prefix = _path_prefix_from_drive_c(line[1:])
            if prefix is not None and prefix not in found:
                found.append(prefix)

    return found


def _named_mac_candidates() -> list[Path]:
    """Return likely broker/Wine roots without recursively scanning the Mac."""

    home = Path.home()
    roots = [
        home / "Library" / "Application Support",
        home / "Library" / "Containers",
        Path("/Applications"),
        home / "Applications",
    ]
    found: list[Path] = []

    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            try:
                if child.is_dir() and _looks_like_mt5_name(child.name) and child not in found:
                    found.append(child)
            except (OSError, PermissionError):
                continue

    wine = home / ".wine"
    if wine.is_dir():
        found.append(wine)
    return found


def _wine_prefixes(*, force_refresh: bool = False) -> tuple[Path, ...]:
    global _prefix_cache

    now = time.monotonic()
    if (
        not force_refresh
        and _prefix_cache is not None
        and now - _prefix_cache[0] <= PREFIX_CACHE_SECONDS
    ):
        return _prefix_cache[1]

    found: list[Path] = []

    def add(candidate: Path) -> None:
        try:
            candidate = candidate.expanduser()
            if candidate.is_dir() and (candidate / "drive_c").is_dir() and candidate not in found:
                found.append(candidate)
        except (OSError, PermissionError):
            return

    for prefix in _candidate_prefixes():
        add(prefix)

    for prefix in _running_mt5_prefixes():
        add(prefix)

    for root in _named_mac_candidates():
        add(root)
        # Broker-branded wrappers may place the actual prefix a few folders
        # below their top-level Application Support or .app directory.
        for candidate in _bounded_dirs(root, max_depth=6):
            add(candidate)

    result = tuple(found)
    _prefix_cache = (now, result)
    return result


def _discover_dirs(patterns: list[str], *, force_refresh: bool = False) -> list[Path]:
    found: list[Path] = []

    for prefix in _wine_prefixes(force_refresh=force_refresh):
        for pattern in patterns:
            try:
                for path in prefix.glob(pattern):
                    if path.is_dir() and path not in found:
                        found.append(path)
            except (OSError, PermissionError):
                continue

    return found


def find_common_files_dirs(*, force_refresh: bool = False) -> list[Path]:
    """Locate MetaTrader's FILE_COMMON directory inside a macOS Wine prefix."""

    override = os.environ.get("FX2ACTIVE_MT5_BRIDGE_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        return [path.parent if path.name == BRIDGE_DIR_NAME else path]

    patterns = [
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/Common/Files",
        "drive_c/users/*/Application Data/MetaQuotes/Terminal/Common/Files",
    ]
    return _discover_dirs(patterns, force_refresh=force_refresh)


def _find_mql5_dirs(*, force_refresh: bool = False) -> list[Path]:
    patterns = [
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal/*/MQL5",
        "drive_c/users/*/Application Data/MetaQuotes/Terminal/*/MQL5",
        "drive_c/Program Files/*/MQL5",
        "drive_c/Program Files (x86)/*/MQL5",
    ]
    found = _discover_dirs(patterns, force_refresh=force_refresh)

    # Some broker wrappers add one extra installation directory beneath
    # Program Files. Search only the known Wine prefixes, not the whole Mac.
    for prefix in _wine_prefixes(force_refresh=force_refresh):
        for base in (
            prefix / "drive_c" / "Program Files",
            prefix / "drive_c" / "Program Files (x86)",
        ):
            if not base.is_dir():
                continue
            for candidate in _bounded_dirs(base, max_depth=4):
                if candidate.name == "MQL5" and candidate not in found:
                    found.append(candidate)
    return found


def find_experts_dirs(*, force_refresh: bool = False) -> list[Path]:
    """Locate or derive installed MT5 MQL5/Experts directories."""

    found: list[Path] = []
    for mql5_dir in _find_mql5_dirs(force_refresh=force_refresh):
        experts = mql5_dir / "Experts"
        if experts not in found:
            found.append(experts)
    return found


def install_bridge_source(source: str | Path) -> list[Path]:
    """Create FX2Active under Experts and copy the bridge source automatically."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Bridge source does not exist: {source_path}")

    installed: list[Path] = []
    experts_dirs = find_experts_dirs(force_refresh=True)
    for experts_dir in experts_dirs:
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
        # MT5 may have been opened after FX2Active started. Refresh prefix
        # discovery before giving up.
        for common_dir in find_common_files_dirs(force_refresh=True):
            candidate = common_dir / BRIDGE_DIR_NAME / SNAPSHOT_FILE
            if candidate.is_file() and candidate not in existing:
                existing.append(candidate)

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

    for common_dir in find_common_files_dirs(force_refresh=True):
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
