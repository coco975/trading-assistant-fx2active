from __future__ import annotations

import hmac
import ipaddress
import json
import secrets
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .runtime_settings import RuntimeSettings, RuntimeSettingsStore
from .system_diagnostics import run_diagnostics, save_report


SESSION_COOKIE = "fx2active_session"


def is_private_client(address: str) -> bool:
    """Return True only for loopback/private IP clients."""

    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


def pin_matches(candidate: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if candidate is None:
        return False
    return hmac.compare_digest(candidate, expected)


class SessionStore:
    """In-memory browser sessions.

    Cookies intentionally have no Expires/Max-Age value, so they are browser
    session cookies. Restarting FX2Active also clears every server-side session.
    """

    def __init__(self) -> None:
        self._tokens: set[str] = set()
        self._lock = threading.Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens.add(token)
        return token

    def contains(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return token in self._tokens

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._tokens.discard(token)


def session_token_from_cookie(header: str | None) -> str | None:
    if not header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else None


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
        self.sessions = SessionStore()

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
        sessions = self.sessions

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

            def _private_client_ok(self) -> bool:
                if not lan_only:
                    return True
                if is_private_client(self.client_address[0]):
                    return True
                self._plain(HTTPStatus.FORBIDDEN, "FX2Active allows private-network access only.")
                return False

            def _authenticated(self) -> bool:
                if not dashboard_pin:
                    return True
                token = session_token_from_cookie(self.headers.get("Cookie"))
                return sessions.contains(token)

            def _require_session(self) -> bool:
                if self._authenticated():
                    return True
                if self.path.startswith("/api/"):
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "authentication required"})
                else:
                    self.send_response(HTTPStatus.SEE_OTHER)
                    self.send_header("Location", "/login.html")
                    self._security_headers()
                    self.end_headers()
                return False

            def _plain(self, status: int, message: str) -> None:
                body = message.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: dict, *, cookie: str | None = None) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                if cookie is not None:
                    self.send_header("Set-Cookie", cookie)
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

            def _read_json_body(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 100_000:
                    raise ValueError("invalid request length")
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("request body must be a JSON object")
                return value

            def do_GET(self) -> None:  # noqa: N802
                if not self._private_client_ok():
                    return
                path = urlparse(self.path).path

                if path == "/api/auth/status":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "required": bool(dashboard_pin),
                            "authenticated": self._authenticated(),
                        },
                    )
                    return

                if dashboard_pin and path in {"/login", "/login.html"}:
                    if self._authenticated():
                        self.send_response(HTTPStatus.SEE_OTHER)
                        self.send_header("Location", "/")
                        self._security_headers()
                        self.end_headers()
                    else:
                        self._serve_file(web_root / "login.html", "text/html; charset=utf-8")
                    return
                if dashboard_pin and path == "/login.js":
                    self._serve_file(web_root / "login.js", "application/javascript; charset=utf-8")
                    return
                if path == "/styles.css":
                    self._serve_file(web_root / "styles.css", "text/css; charset=utf-8")
                    return

                if not self._require_session():
                    return

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
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:  # noqa: N802
                if not self._private_client_ok():
                    return
                path = urlparse(self.path).path

                if path == "/api/auth/login":
                    if not dashboard_pin:
                        self._json(HTTPStatus.OK, {"ok": True, "authenticated": True})
                        return
                    try:
                        payload = self._read_json_body()
                        candidate = str(payload.get("pin", ""))
                    except (ValueError, TypeError, json.JSONDecodeError) as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                        return
                    if not pin_matches(candidate, dashboard_pin):
                        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "incorrect access PIN"})
                        return
                    token = sessions.create()
                    cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"
                    self._json(HTTPStatus.OK, {"ok": True, "authenticated": True}, cookie=cookie)
                    return

                if path == "/api/auth/logout":
                    token = session_token_from_cookie(self.headers.get("Cookie"))
                    sessions.revoke(token)
                    cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                    self._json(HTTPStatus.OK, {"ok": True}, cookie=cookie)
                    return

                if not self._require_session():
                    return

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
                    payload = self._read_json_body()
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
