"""In-memory MJPEG preview for the camera frames already captured by the app."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class LatestFrame:
    """Keep only the newest JPEG frame; frames are never written to disk."""

    def __init__(self):
        self._condition = threading.Condition()
        self._sequence = 0
        self._jpeg: bytes | None = None
        self._updated_at: float | None = None

    def publish(self, jpeg: bytes) -> None:
        if not jpeg:
            raise ValueError("JPEG frame must not be empty")
        with self._condition:
            self._sequence += 1
            self._jpeg = jpeg
            self._updated_at = time.monotonic()
            self._condition.notify_all()

    def wait_for_frame(self, after_sequence: int, timeout: float) -> tuple[int, bytes] | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sequence <= after_sequence or self._jpeg is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return self._sequence, self._jpeg

    def status(self) -> tuple[int, float | None]:
        with self._condition:
            age = None if self._updated_at is None else time.monotonic() - self._updated_at
            return self._sequence, age


class VideoServer:
    """Serve the preview page, camera health, and a multipart MJPEG stream."""

    def __init__(self, frames: LatestFrame, host: str, port: int, stale_after_s: float):
        self.frames = frames
        self.host = host
        self.port = port
        self.stale_after_s = stale_after_s
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        page = (Path(__file__).parent.parent / "web" / "index.html").read_bytes()
        frames = self.frames
        stale_after_s = self.stale_after_s

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlsplit(self.path).path
                if path in ("/", "/index.html"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(page)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(page)
                elif path == "/health":
                    sequence, age = frames.status()
                    ready = age is not None and age <= stale_after_s
                    body = json.dumps({"camera_ready": ready}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/video.mjpg":
                    self._stream()
                else:
                    self.send_error(404)

            def _stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Connection", "close")
                self.end_headers()
                sequence = 0
                try:
                    while True:
                        result = frames.wait_for_frame(sequence, timeout=10.0)
                        if result is None:
                            continue
                        sequence, jpeg = result
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                            + jpeg
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    return

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("video server has not been started")
        return self._server.server_address[1]

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
