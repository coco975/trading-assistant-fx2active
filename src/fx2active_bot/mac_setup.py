from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import mac_bridge


@dataclass
class MacBridgeSetupReport:
    apps: list[Path] = field(default_factory=list)
    prefixes: list[Path] = field(default_factory=list)
    install_roots: list[Path] = field(default_factory=list)
    installed_sources: list[Path] = field(default_factory=list)
    compiled_sources: list[Path] = field(default_factory=list)
    launched_app: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def source_ready(self) -> bool:
        return bool(self.installed_sources)

    @property
    def compile_ready(self) -> bool:
        return bool(self.compiled_sources)


def _looks_like_mt5_app(path: Path) -> bool:
    name = path.name.lower().replace(" ", "")
    return any(token in name for token in ("metatrader5", "metatrader", "mt5", "exness"))


def find_mt5_apps() -> list[Path]:
    """Find browser-installed MetaTrader/broker app bundles without Spotlight."""

    found: list[Path] = []
    for root in (Path("/Applications"), Path.home() / "Applications"):
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            try:
                if child.is_dir() and child.suffix.lower() == ".app" and _looks_like_mt5_app(child):
                    found.append(child)
            except (OSError, PermissionError):
                continue
    return sorted(set(found), key=lambda path: path.name.lower())


def _process_table() -> str:
    try:
        result = subprocess.run(
            ["ps", "-axo", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def mt5_is_running() -> bool:
    for line in _process_table().splitlines():
        lower = line.lower()
        if "terminal64.exe" in lower or "metaeditor64.exe" in lower:
            return True
    return False


def launch_single_detected_mt5_app(apps: list[Path] | None = None) -> Path | None:
    """Launch MT5 only when there is one unambiguous installed app."""

    if mt5_is_running():
        return None
    candidates = apps if apps is not None else find_mt5_apps()
    if len(candidates) != 1:
        return None
    app = candidates[0]
    try:
        subprocess.run(["open", str(app)], check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return app


def _shallow_application_support_prefixes() -> list[Path]:
    """Catch broker-branded Wine prefixes even when their folder name is unfamiliar."""

    root = Path.home() / "Library" / "Application Support"
    if not root.is_dir():
        return []
    found: list[Path] = []
    try:
        first_level = list(root.iterdir())
    except (OSError, PermissionError):
        return found

    for child in first_level:
        try:
            if not child.is_dir():
                continue
            if (child / "drive_c").is_dir():
                found.append(child)
                continue
            # Old broker wrappers commonly keep Wine prefixes one or two levels down.
            for nested in child.iterdir():
                if nested.is_dir() and (nested / "drive_c").is_dir():
                    found.append(nested)
        except (OSError, PermissionError):
            continue
    return found


def discover_wine_prefixes(*, force_refresh: bool = False) -> list[Path]:
    found: list[Path] = []
    for prefix in mac_bridge._wine_prefixes(force_refresh=force_refresh):
        if prefix not in found:
            found.append(prefix)
    for prefix in _shallow_application_support_prefixes():
        if prefix not in found:
            found.append(prefix)
    return found


def _program_files_roots(prefix: Path) -> list[Path]:
    roots: list[Path] = []
    for name in ("Program Files", "Program Files (x86)"):
        root = prefix / "drive_c" / name
        if root.is_dir():
            roots.append(root)
    return roots


def discover_mt5_install_roots(*, force_refresh: bool = False) -> list[Path]:
    """Find terminal install roots even when MQL5/Experts has not been created yet."""

    found: list[Path] = []
    for prefix in discover_wine_prefixes(force_refresh=force_refresh):
        for program_files in _program_files_roots(prefix):
            try:
                children = list(program_files.iterdir())
            except (OSError, PermissionError):
                continue
            for child in children:
                try:
                    if not child.is_dir():
                        continue
                    has_terminal = (child / "terminal64.exe").is_file() or (child / "terminal.exe").is_file()
                    has_editor = (child / "metaeditor64.exe").is_file() or (child / "metaeditor.exe").is_file()
                    if (has_terminal or has_editor) and child not in found:
                        found.append(child)
                except (OSError, PermissionError):
                    continue
    return found


def _prefix_for_path(path: Path, prefixes: list[Path]) -> Path | None:
    resolved = path.resolve()
    for prefix in prefixes:
        try:
            resolved.relative_to(prefix.resolve())
        except ValueError:
            continue
        return prefix
    return None


def _copy_bridge_to_install_root(source: Path, install_root: Path) -> Path:
    """Create MQL5/Experts/FX2Active when missing and install bridge source."""

    target_dir = install_root / "MQL5" / "Experts" / mac_bridge.BRIDGE_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if not target.is_file() or target.read_bytes() != source.read_bytes():
        shutil.copyfile(source, target)
    return target


def _wine_launchers(apps: list[Path]) -> list[Path]:
    found: list[Path] = []

    # The official web-installed package uses Contents/SharedSupport/wine/bin/wine64.
    relative_candidates = (
        "Contents/SharedSupport/wine/bin/wine64",
        "Contents/SharedSupport/wine/bin/wine",
        "Contents/Resources/wine/bin/wine64",
        "Contents/Resources/wine/bin/wine",
    )
    for app in apps:
        for relative in relative_candidates:
            candidate = app / relative
            if candidate.is_file() and os.access(candidate, os.X_OK) and candidate not in found:
                found.append(candidate)

    for command in ("wine64", "wine"):
        resolved = shutil.which(command)
        if resolved:
            candidate = Path(resolved)
            if candidate not in found:
                found.append(candidate)

    # A broker-branded package may expose a different bundle path. Reuse the
    # Wine executable visible in the live MT5 command line when available.
    for line in _process_table().splitlines():
        if "terminal64.exe" not in line.lower() and "metaeditor64.exe" not in line.lower():
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        for part in parts:
            candidate = Path(part)
            if candidate.name.lower() in {"wine64", "wine"} and candidate.is_file():
                if candidate not in found:
                    found.append(candidate)
    return found


def _windows_path(path: Path, prefix: Path) -> str | None:
    try:
        relative = path.resolve().relative_to((prefix / "drive_c").resolve())
    except ValueError:
        return None
    return "C:\\" + "\\".join(relative.parts)


def _metaeditor_for_source(source: Path) -> Path | None:
    current = source
    for parent in source.parents:
        if parent.name == "MQL5":
            current = parent.parent
            break
    for name in ("metaeditor64.exe", "metaeditor.exe"):
        candidate = current / name
        if candidate.is_file():
            return candidate
    return None


def try_compile_bridge_source(
    source: Path,
    *,
    prefixes: list[Path],
    apps: list[Path],
    timeout_seconds: float = 25.0,
) -> tuple[bool, str]:
    """Best-effort unattended MetaEditor compile using the installed Wine bundle."""

    if not mac_bridge.bridge_source_needs_compile(source):
        return True, "already compiled"

    prefix = _prefix_for_path(source, prefixes)
    if prefix is None:
        return False, "could not match bridge source to a Wine prefix"
    metaeditor = _metaeditor_for_source(source)
    if metaeditor is None:
        return False, "metaeditor64.exe was not found beside the MT5 installation"
    windows_source = _windows_path(source, prefix)
    if windows_source is None:
        return False, "could not convert bridge path for MetaEditor"

    launchers = _wine_launchers(apps)
    if not launchers:
        return False, "the installed MT5 Wine launcher was not found"

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    command = [
        str(launchers[0]),
        str(metaeditor),
        f"/compile:{windows_source}",
        "/log",
    ]
    try:
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"automatic MetaEditor compile could not start: {exc}"

    compiled = source.with_suffix(".ex5")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not mac_bridge.bridge_source_needs_compile(source):
            return True, "compiled automatically"
        time.sleep(0.5)

    log_path = source.with_suffix(".log")
    if log_path.is_file():
        try:
            lines = [line.strip() for line in log_path.read_text(errors="replace").splitlines() if line.strip()]
            if lines:
                return False, f"MetaEditor did not create a current EX5: {lines[-1]}"
        except OSError:
            pass
    return False, "MetaEditor ran but a current FX2ActiveBridge.ex5 was not produced"


def prepare_mac_bridge(source: str | Path) -> MacBridgeSetupReport:
    """Discover a web-installed MT5, create bridge folders, copy and compile source."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Bridge source does not exist: {source_path}")

    report = MacBridgeSetupReport()
    report.apps = find_mt5_apps()
    report.prefixes = discover_wine_prefixes(force_refresh=True)

    # The official browser installer creates the Wine prefix after the app has
    # been opened. If exactly one MT5 app is installed, start it automatically.
    if not report.prefixes and report.apps:
        report.launched_app = launch_single_detected_mt5_app(report.apps)
        if report.launched_app is not None:
            for _ in range(8):
                time.sleep(1.0)
                mac_bridge.clear_prefix_cache()
                report.prefixes = discover_wine_prefixes(force_refresh=True)
                if report.prefixes:
                    break

    report.install_roots = discover_mt5_install_roots(force_refresh=True)

    installed: list[Path] = []
    for install_root in report.install_roots:
        try:
            target = _copy_bridge_to_install_root(source_path, install_root)
            if target not in installed:
                installed.append(target)
        except PermissionError:
            report.warnings.append(
                f"No write permission for MT5 data folder: {install_root}. "
                "A normal web-installed MT5 under your user Library should not require sudo."
            )
        except OSError as exc:
            report.warnings.append(f"Could not prepare {install_root}: {exc}")

    # Preserve support for older AppData/hashed-terminal layouts already handled
    # by mac_bridge.install_bridge_source().
    try:
        for target in mac_bridge.install_bridge_source(source_path):
            if target not in installed:
                installed.append(target)
    except OSError as exc:
        report.warnings.append(f"Legacy MT5 bridge path check failed: {exc}")

    report.installed_sources = installed

    for target in installed:
        ok, message = try_compile_bridge_source(
            target,
            prefixes=report.prefixes,
            apps=report.apps,
        )
        if ok:
            report.compiled_sources.append(target)
        elif mac_bridge.bridge_source_needs_compile(target):
            report.warnings.append(f"{target}: {message}")

    if not report.install_roots and not installed:
        if not report.apps:
            report.warnings.append(
                "No MetaTrader 5/Exness macOS app or Wine data directory was detected."
            )
        elif len(report.apps) > 1 and not mt5_is_running():
            report.warnings.append(
                "Multiple MT5 apps are installed. Open the broker terminal you want FX2Active to use once, then restart FX2Active."
            )
        else:
            report.warnings.append(
                "MT5 is installed but its Wine data directory is not ready yet. Open MT5 once and restart FX2Active."
            )

    return report
