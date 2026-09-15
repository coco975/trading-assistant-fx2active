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
BRIDGE_PROTOCOL_VERSION = 2
BRIDGE_SOURCE_VERSION = "1.10"
BRIDGE_SOURCE_FILE = "FX2ActiveBridge.mq5"
BRIDGE_BINARY_FILE = "FX2ActiveBridge.ex5"
SNAPSHOT_FILE = "snapshot.json"
REQUESTED_SYMBOL_FILE = "requested_symbol.txt"
BRIDGE_STALE_SECONDS = 15.0
BRIDGE_CLOCK_SKEW_SECONDS = 5.0
PREFIX_CACHE_SECONDS = 10.0
SNAPSHOT_READ_ATTEMPTS = 3
SNAPSHOT_READ_DELAY_SECONDS = 0.05

_prefix_cache: tuple[float, tuple[Path, ...]] | None = None


def clear_prefix_cache() -> None:
    global _prefix_cache
    _prefix_cache = None


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
    return prefix if prefix.is_dir() and (prefix / "drive_c").is_dir() else None


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
            if (
                candidate.is_dir()
                and (candidate / "drive_c").is_dir()
                and candidate not in found
            ):
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
            timeout=2,
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

    # Only fall back to lsof if the process command did not expose the prefix.
    # Limit this to a few processes and a short timeout so startup cannot hang.
    if found:
        return found

    for pid in pids[:3]:
        try:
            opened = subprocess.run(
                ["lsof", "-Fn", "-p", pid],
                check=False,
                capture_output=True,
                text=True,
                timeout=1,
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


def _terminal_roots(*, force_refresh: bool = False) -> list[Path]:
    patterns = [
        "drive_c/users/*/AppData/Roaming/MetaQuotes/Terminal",
        "drive_c/users/*/Application Data/MetaQuotes/Terminal",
    ]
    return _discover_dirs(patterns, force_refresh=force_refresh)


def find_common_files_dirs(*, force_refresh: bool = False) -> list[Path]:
    """Locate MetaTrader's FILE_COMMON directory inside a macOS Wine prefix."""

    override = os.environ.get("FX2ACTIVE_MT5_BRIDGE_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        return [path.parent if path.name == BRIDGE_DIR_NAME else path]

    found: list[Path] = []
    for terminal_root in _terminal_roots(force_refresh=force_refresh):
        common_files = terminal_root / "Common" / "Files"
        if common_files not in found:
            found.append(common_files)
    return found


def _find_mql5_dirs(*, force_refresh: bool = False) -> list[Path]:
    found: list[Path] = []

    for terminal_root in _terminal_roots(force_refresh=force_refresh):
        try:
            children = list(terminal_root.iterdir())
        except (OSError, PermissionError):
            continue

        for child in children:
            if child.name == "Common" or not child.is_dir():
                continue
            mql5_dir = child / "MQL5"
            if mql5_dir.is_dir() and mql5_dir not in found:
                found.append(mql5_dir)

        # Broker wrappers occasionally add one extra directory level. Search
        # only underneath this terminal data root, never the whole Mac.
        for candidate in _bounded_dirs(terminal_root, max_depth=4):
            if candidate.name == "MQL5" and candidate.is_dir() and candidate not in found:
                found.append(candidate)

    return found


def find_experts_dirs(*, force_refresh: bool = False) -> list[Path]:
    """Locate or derive installed MT5 MQL5/Experts directories."""

    return [path / "Experts" for path in _find_mql5_dirs(force_refresh=force_refresh)]


def _same_file_contents(first: Path, second: Path) -> bool:
    try:
        return first.is_file() and second.is_file() and first.read_bytes() == second.read_bytes()
    except OSError:
        return False


def install_bridge_source(source: str | Path) -> list[Path]:
    """Create FX2Active under Experts and copy the latest bridge source."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Bridge source does not exist: {source_path}")

    installed: list[Path] = []
    for experts_dir in find_experts_dirs(force_refresh=True):
        try:
            target_dir = experts_dir / BRIDGE_DIR_NAME
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source_path.name
            if not _same_file_contents(source_path, target):
                shutil.copyfile(source_path, target)
            installed.append(target)
        except OSError:
            continue
    return installed


def find_installed_bridge_sources(*, force_refresh: bool = False) -> list[Path]:
    found: list[Path] = []
    for experts_dir in find_experts_dirs(force_refresh=force_refresh):
        candidate = experts_dir / BRIDGE_DIR_NAME / BRIDGE_SOURCE_FILE
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    return found


def find_compiled_bridge_binaries(*, force_refresh: bool = False) -> list[Path]:
    found: list[Path] = []
    for experts_dir in find_experts_dirs(force_refresh=force_refresh):
        candidate = experts_dir / BRIDGE_DIR_NAME / BRIDGE_BINARY_FILE
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    return found


def bridge_source_needs_compile(source_path: str | Path) -> bool:
    source = Path(source_path)
    compiled = source.with_suffix(".ex5")
    if not compiled.is_file():
        return True
    try:
        return compiled.stat().st_mtime < source.stat().st_mtime
    except OSError:
        return True


def _snapshot_candidates(*, force_refresh: bool = False) -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("FX2ACTIVE_MT5_BRIDGE_DIR", "").strip()
    if override:
        base = Path(override).expanduser()
        candidate = base / SNAPSHOT_FILE if base.name == BRIDGE_DIR_NAME else base / BRIDGE_DIR_NAME / SNAPSHOT_FILE
        candidates.append(candidate)

    for common_dir in find_common_files_dirs(force_refresh=force_refresh):
        candidate = common_dir / BRIDGE_DIR_NAME / SNAPSHOT_FILE
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def find_snapshot_path() -> Path | None:
    existing = [path for path in _snapshot_candidates() if path.is_file()]
    if not existing:
        existing = [path for path in _snapshot_candidates(force_refresh=True) if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def validate_snapshot(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("FX2Active MT5 bridge snapshot has an invalid format")

    try:
        protocol = int(payload.get("protocol_version", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("FX2Active MT5 bridge protocol value is invalid") from exc

    if protocol != BRIDGE_PROTOCOL_VERSION:
        raise RuntimeError(
            "FX2Active MT5 bridge is out of date "
            f"(protocol {protocol}, expected {BRIDGE_PROTOCOL_VERSION}). "
            "Recompile the latest FX2ActiveBridge.mq5 in MetaEditor."
        )

    for key in ("terminal", "account", "symbol"):
        if not isinstance(payload.get(key), dict):
            raise RuntimeError(f"FX2Active MT5 bridge snapshot is missing '{key}' data")
    if not isinstance(payload.get("rates"), list):
        raise RuntimeError("FX2Active MT5 bridge snapshot is missing rates data")

    heartbeat = payload.get("heartbeat_utc", payload.get("heartbeat"))
    try:
        if float(heartbeat or 0.0) <= 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise RuntimeError("FX2Active MT5 bridge snapshot has an invalid heartbeat") from exc


def _read_snapshot(path: Path) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(SNAPSHOT_READ_ATTEMPTS):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate_snapshot(payload)
            return payload
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < SNAPSHOT_READ_ATTEMPTS:
                time.sleep(SNAPSHOT_READ_DELAY_SECONDS)

    if isinstance(last_error, RuntimeError):
        raise last_error
    raise RuntimeError(f"Could not read the FX2Active MT5 bridge snapshot: {last_error}")


def load_snapshot() -> tuple[dict[str, Any], Path]:
    candidates = [path for path in _snapshot_candidates() if path.is_file()]
    if not candidates:
        candidates = [path for path in _snapshot_candidates(force_refresh=True) if path.is_file()]
    if not candidates:
        raise FileNotFoundError(
            "FX2Active MT5 bridge snapshot was not found. "
            "Compile and attach FX2ActiveBridge to one MetaTrader 5 chart."
        )

    errors: list[str] = []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            return _read_snapshot(path), path
        except RuntimeError as exc:
            errors.append(f"{path}: {exc}")

    raise RuntimeError(errors[0] if errors else "No readable FX2Active bridge snapshot was found")


def snapshot_age_seconds(snapshot: dict[str, Any]) -> float:
    heartbeat = float(snapshot.get("heartbeat_utc", snapshot.get("heartbeat", 0.0)) or 0.0)
    if heartbeat <= 0:
        return float("inf")
    delta = time.time() - heartbeat
    if delta < -BRIDGE_CLOCK_SKEW_SECONDS:
        return float("inf")
    return max(0.0, delta)


def snapshot_is_fresh(snapshot: dict[str, Any]) -> bool:
    return snapshot_age_seconds(snapshot) <= BRIDGE_STALE_SECONDS


def _write_symbol_file(bridge_dir: Path, symbol: str) -> Path:
    bridge_dir.mkdir(parents=True, exist_ok=True)
    target = bridge_dir / REQUESTED_SYMBOL_FILE
    temporary = bridge_dir / f".{REQUESTED_SYMBOL_FILE}.tmp"
    temporary.write_text(symbol + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def write_requested_symbol(symbol: str) -> Path | None:
    symbol = symbol.strip()
    if not symbol:
        return None
    if len(symbol) > 64 or any(character in symbol for character in "\r\n\x00"):
        raise ValueError("Invalid MT5 symbol name")

    snapshot_path = find_snapshot_path()
    if snapshot_path is not None:
        return _write_symbol_file(snapshot_path.parent, symbol)

    for common_dir in find_common_files_dirs(force_refresh=True):
        try:
            return _write_symbol_file(common_dir / BRIDGE_DIR_NAME, symbol)
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
