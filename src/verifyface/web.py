"""A complete browser app with no extra dependencies.

``python -m verifyface serve`` starts a small threaded HTTP server that serves
one page with three tabs — live scan, photo verification and enrollment.  It
uses only the Python standard library plus what verifyface already depends on.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from . import _meta
from .errors import VerifyFaceError
from .verify import Verifier

MAX_BODY = 24 * 1024 * 1024          # 24 MB per request
SESSION_TTL = 10 * 60                # 10 minutes
WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"


class AppState:
    """Shared state for the demo server (verifier + live sessions)."""

    def __init__(self, vault: Optional[str] = None) -> None:
        self.verifier = Verifier(vault=vault)
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    # -- live sessions ----------------------------------------------------- #
    def new_session(self, identity: Optional[str], mode: str, actions: int) -> Dict[str, Any]:
        from .camera import LiveSession

        session = LiveSession(
            identity=identity, verifier=self.verifier, mode=mode, actions=actions
        )
        session_id = uuid.uuid4().hex
        state = session.begin()
        with self.lock:
            self.sessions[session_id] = {
                "session": session,
                "created": time.time(),
                "mode": mode,
                "identity": identity,
            }
            self._cleanup()
        state["session_id"] = session_id
        return state

    def feed(self, session_id: str, frame: Any) -> Dict[str, Any]:
        with self.lock:
            entry = self.sessions.get(session_id)
        if entry is None:
            raise KeyError("Unknown or expired live session. Start again.")
        session = entry["session"]
        state = session.feed(frame)
        state["session_id"] = session_id
        if state["status"] == "done" and session.result is not None:
            state["result"] = session.result.as_dict()
            preview = session.preview_data_uri()
            if preview:
                state["preview"] = preview
            with self.lock:
                self.sessions.pop(session_id, None)
        return state

    def _cleanup(self) -> None:
        now = time.time()
        for key, entry in list(self.sessions.items()):
            if now - entry["created"] > SESSION_TTL:
                self.sessions.pop(key, None)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


def make_handler(state: AppState):
    """Build a request handler bound to ``state``."""

    class Handler(BaseHTTPRequestHandler):
        server_version = f"verifyface/{_meta.__version__}"
        protocol_version = "HTTP/1.1"

        # -- helpers ---------------------------------------------------- #
        def log_message(self, fmt: str, *args) -> None:  # quieter console
            if "/api/" in (fmt % args):
                return
            super().log_message(fmt, *args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # allow the app to be embedded in previews / iframes
            self.send_header("X-Frame-Options", "ALLOWALL")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"ok": False, "error": message})

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                raise ValueError("Empty request body.")
            if length > MAX_BODY:
                raise ValueError("Request too large.")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                raise ValueError("Body must be JSON.") from None
            if not isinstance(data, dict):
                raise ValueError("Body must be a JSON object.")
            return data

        # -- static ------------------------------------------------------ #
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                html = (WEBAPP_DIR / "index.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
                return
            if path == "/api/list":
                try:
                    items = []
                    for name in state.verifier.identities():
                        try:
                            items.append(state.verifier.profile(name).as_dict())
                        except Exception as exc:
                            items.append({"identity": name, "error": str(exc)})
                    self._json(200, {"ok": True, "identities": items})
                except Exception as exc:
                    self._error(500, str(exc))
                return
            if path == "/api/health":
                self._json(200, {"ok": True, "version": _meta.__version__,
                                 "developer": _meta.__author__})
                return
            if path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
                return
            # any other static file inside the webapp folder
            candidate = (WEBAPP_DIR / path.lstrip("/")).resolve()
            if WEBAPP_DIR in candidate.parents and candidate.is_file():
                ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                self._send(200, candidate.read_bytes(), ctype)
                return
            self._error(404, "Not found.")

        def do_OPTIONS(self) -> None:
            self._send(204, b"", "text/plain")

        # -- API --------------------------------------------------------- #
        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                data = self._read_json()
            except ValueError as exc:
                self._error(400, str(exc))
                return

            try:
                if path == "/api/enroll":
                    self._handle_enroll(data)
                elif path == "/api/verify":
                    self._handle_verify(data)
                elif path == "/api/identify":
                    self._handle_identify(data)
                elif path == "/api/compare":
                    self._handle_compare(data)
                elif path == "/api/delete":
                    name = str(data.get("name", "")).strip()
                    removed = state.verifier.remove(name)
                    self._json(200, {"ok": True, "deleted": removed})
                elif path == "/api/live/begin":
                    identity = (data.get("name") or "").strip() or None
                    mode = str(data.get("mode") or ("verify" if identity else "capture"))
                    if mode in {"verify", "enroll"} and not identity:
                        self._error(400, "Live verification needs a name.")
                        return
                    payload = state.new_session(identity, mode, int(data.get("actions", 2)))
                    payload["ok"] = True
                    self._json(200, payload)
                elif path == "/api/live/frame":
                    session_id = str(data.get("session_id", ""))
                    image = data.get("image")
                    if not image:
                        self._error(400, "Missing frame.")
                        return
                    payload = state.feed(session_id, image)
                    payload["ok"] = True
                    self._json(200, payload)
                else:
                    self._error(404, "Unknown endpoint.")
            except VerifyFaceError as exc:
                self._error(400, str(exc).split("\n")[0])
            except KeyError as exc:
                self._error(404, str(exc).strip("'\""))
            except Exception as exc:  # pragma: no cover - defensive
                self._error(500, f"{type(exc).__name__}: {exc}")

        # -- individual endpoints ---------------------------------------- #
        def _handle_enroll(self, data: dict) -> None:
            name = str(data.get("name", "")).strip()
            images = data.get("images") or []
            if not name:
                self._error(400, "Please enter a name.")
                return
            if not isinstance(images, list) or not images:
                self._error(400, "Please add at least one photo.")
                return
            if len(images) > 6:
                images = images[:6]
            result = state.verifier.enroll(
                name, images, overwrite=bool(data.get("overwrite", True))
            )
            payload = result.as_dict()
            payload.update(ok=True, message=result.explain())
            self._json(200, payload)

        def _handle_verify(self, data: dict) -> None:
            name = str(data.get("name", "")).strip()
            image = data.get("image")
            if not name or not image:
                self._error(400, "A name and a photo are required.")
                return
            result = state.verifier.verify(name, image)
            payload = result.as_dict()
            payload.update(ok=True, message=result.explain())
            self._json(200, payload)

        def _handle_identify(self, data: dict) -> None:
            image = data.get("image")
            if not image:
                self._error(400, "A photo is required.")
                return
            result = state.verifier.identify(image)
            payload = result.as_dict()
            payload.update(ok=True, message=result.explain())
            self._json(200, payload)

        def _handle_compare(self, data: dict) -> None:
            image_a, image_b = data.get("a"), data.get("b")
            if not image_a or not image_b:
                self._error(400, "Two photos are required.")
                return
            result = state.verifier.compare(image_a, image_b)
            payload = result.as_dict()
            payload.update(ok=True, message=result.explain())
            self._json(200, payload)

    return Handler


def create_server(
    host: str = "127.0.0.1", port: int = 8000, vault: Optional[str] = None
) -> Tuple[ThreadingHTTPServer, AppState]:
    """Create (but do not start) the demo server."""
    state = AppState(vault=vault)
    handler = make_handler(state)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server, state


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    vault: Optional[str] = None,
    *,
    open_browser: bool = False,
) -> int:
    """Run the demo server until Ctrl+C."""
    server, state = create_server(host, port, vault)
    display_host = "localhost" if host in {"127.0.0.1", "0.0.0.0"} else host
    url = f"http://{display_host}:{port}/"
    print(f"{_meta.BANNER}")
    print(f"Open {url} in your browser  (Ctrl+C to stop)")
    print(f"vault: {state.verifier.vault.path}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


__all__ = ["serve", "create_server", "AppState", "make_handler"]
