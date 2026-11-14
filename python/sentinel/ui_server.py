"""Setup / development HTTP dashboard (features 003–004). Never start when DEV_BUILD is false."""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from sentinel.preview import DevPreviewState

CommandHandler = Callable[[str, dict], dict]


def create_ui_server(
    allowed: bool,
    port: int,
    assets_dir: Path,
    get_snapshot: Callable[[], dict],
    preview: DevPreviewState,
    on_command: CommandHandler | None = None,
) -> ThreadingHTTPServer | None:
    """Bind a LAN UI server, or return None when not allowed (product builds)."""
    if not allowed:
        return None
    assets_dir = Path(assets_dir)
    handler = _make_handler(assets_dir, get_snapshot, preview, on_command or (lambda n, b: {"ok": False}))
    return ThreadingHTTPServer(("0.0.0.0", port), handler)


def start_ui_server_thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name="setup-ui", daemon=True)
    thread.start()
    return thread


def _make_handler(
    assets_dir: Path,
    get_snapshot: Callable[[], dict],
    preview: DevPreviewState,
    on_command: CommandHandler,
):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                self._file(assets_dir / "index.html", "text/html; charset=utf-8")
            elif path == "/app.js":
                self._file(assets_dir / "app.js", "application/javascript; charset=utf-8")
            elif path == "/style.css":
                self._file(assets_dir / "style.css", "text/css; charset=utf-8")
            elif path.startswith("/fonts/") or path.startswith("/img/"):
                rel = path.lstrip("/")
                target = (assets_dir / rel).resolve()
                if not str(target).startswith(str(assets_dir.resolve())):
                    self.send_error(404)
                    return
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self._file(target, ctype)
            elif path == "/api/snapshot":
                self._json(200, get_snapshot())
            elif path == "/api/preview":
                self._json(200, {"state": preview.state_name})
            elif path == "/api/preview/frame":
                frame = preview.latest_frame()
                if frame is None:
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(frame)
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
            except ValueError:
                self._json(400, {"ok": False, "error": "bad_json"})
                return

            if path == "/api/preview/on":
                preview.turn_on()
                self._json(200, {"ok": True, "state": preview.state_name})
            elif path == "/api/preview/off":
                preview.turn_off()
                self._json(200, {"ok": True, "state": preview.state_name})
            elif path in (
                "/api/sensitivity", "/api/noise_threshold", "/api/snooze",
                "/api/calibrate", "/api/summary", "/api/confidence",
            ):
                name = path.rsplit("/", 1)[-1]
                try:
                    result = on_command(name, body)
                except Exception as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                code = 200 if result.get("ok", True) else 400
                self._json(code, result)
            else:
                self.send_error(404)

        def _json(self, code: int, body: dict):
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _file(self, path: Path, content_type: str):
            if not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler
