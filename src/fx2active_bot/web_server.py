from __future__ import annotations

import base64
import hmac
import ipaddress
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .runtime_settings import RuntimeSettings, RuntimeSettingsStore
from .system_diagnostics import run_diagnostics, save_report


def is_private_client(address: str) -> bool:
    """Return True only for loopback/private IP clients.

    LAN mode deliberately refuses public-source addresses even if the host OS or
    router is later misconfigured. This is an extra guard, not a replacement for
    keeping router port forwarding disabled.
    """

    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


def basic_auth_matches(header: str | None, pin: str | None) -> bool:
    if not pin:
        return True
    if not header:
        return False
    try:
        scheme, token = header.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
        username, separator, password = decoded.partition(":")
        if not separator:
            return False
    except (ValueError, UnicodeDecodeError):
        return False

    return hmac.compare_digest(username, "fx2active") and hmac.compare_digest(password, pin)


class ControlPanelServer:
    def __init__(
        self,
        *,
        settings_path: str | Path,
        web_root: str | Path,
        status_path: str | Path | None = None,
        diagnostics_path: str | Path | None = None,
        host: str = "127.0.0.1",
        port: int = 8080,
        dashboard_pin: str | None = None,
        lan_only: bool = False,
    ) -> None:
        self.store = RuntimeSettingsStore(settings_path)
        self.settings_path = Path(settings_path)
        self.web_root = Path(web_root)
        self.status_path = Path(status_path) if status_path else None
        self.diagnostics_path = Path(diagnostics_path) if diagnostics_path else None
        self.host = host
        self.port = port
        self.dashboard_pin = dashboard_pin
        self.lan_only = lan_only

    def serve_forever(self) -> None:
        store = self.store
        settings_path = self.settings_path
        web_root = self.web_root
        status_path = self.status_path
        diagnostics_path = self.diagnostics_path
        host = self.host
        port = self.port
        dashboard_pin = self.dashboard_pin
        lan_only = self.lan_only

        class Handler(BaseHTTPRequestHandler):
            def _security_headers(self) -> None:
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
                )

            def _plain(self, status: int, message: str, *, auth_challenge: bool = False) -> None:
                body = message.encode("utf-8")
                self.send_response(status)
                if auth_challenge:
                    self.send_header(
                        "WWW-Authenticate",
                        'Basic realm="FX2Active Local Dashboard", charset="UTF-8"',
                    )
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)

            def _ensure_access(self) -> bool:
                client_address = self.client_address[0]
                if lan_only and not is_private_client(client_address):
                    self._plain(HTTPStatus.FORBIDDEN, "FX2Active allows private-network access only.")
                    return False
                if dashboard_pin and not basic_auth_matches(
                    self.headers.get("Authorization"), dashboard_pin
                ):
                    self._plain(
                        HTTPStatus.UNAUTHORIZED,
                        "FX2Active dashboard authentication required.",
                        auth_challenge=True,
                    )
                    return False
                return True

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)

            def _serve_file(self, path: Path, content_type: str) -> None:
                if not path.exists() or not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)

            def _load_json_file(self, path: Path | None, fallback: dict) -> dict:
                if path is None or not path.exists():
                    return fallback
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return fallback

            def do_GET(self) -> None:  # noqa: N802
                if not self._ensure_access():
                    return
                path = urlparse(self.path).path
                if path == "/api/settings":
                    self._json(HTTPStatus.OK, store.load().to_dict())
                    return
                if path == "/api/system/status":
                    self._json(
                        HTTPStatus.OK,
                        self._load_json_file(
                            status_path,
                            {
                                "worker_online": False,
                                "mt5_connected": False,
                                "message": "Waiting for local worker status...",
                            },
                        ),
                    )
                    return
                if path == "/api/system/diagnostics":
                    self._json(
                        HTTPStatus.OK,
                        self._load_json_file(
                            diagnostics_path,
                            {"ready": False, "checks": [], "details": {}},
                        ),
                    )
                    return
                if path in {"/", "/index.html"}:
                    self._serve_file(web_root / "index.html", "text/html; charset=utf-8")
                    return
                if path == "/app.js":
                    self._serve_file(web_root / "app.js", "application/javascript; charset=utf-8")
                    return
                if path == "/styles.css":
                    self._serve_file(web_root / "styles.css", "text/css; charset=utf-8")
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:  # noqa: N802
                if not self._ensure_access():
                    return
                path = urlparse(self.path).path
                if path == "/api/system/diagnose":
                    try:
                        report = run_diagnostics(
                            settings_path=settings_path,
                            host=host,
                            port=port,
                            include_port_check=False,
                        )
                        if diagnostics_path is not None:
                            save_report(report, diagnostics_path)
                        self._json(HTTPStatus.OK, report)
                    except Exception as exc:
                        self._json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {"ready": False, "checks": [], "error": str(exc)},
                        )
                    return

                if path != "/api/settings":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 100_000:
                        raise ValueError("invalid request length")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    settings = RuntimeSettings.from_dict(payload)
                    store.save(settings)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                self._json(HTTPStatus.OK, {"ok": True, "settings": settings.to_dict()})

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        server.serve_forever()
