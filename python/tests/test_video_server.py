import json
import threading
import time
import unittest
from urllib.request import urlopen

from sentinel.video_server import LatestFrame, VideoServer


class VideoServerTests(unittest.TestCase):
    def setUp(self):
        self.frames = LatestFrame()
        self.server = VideoServer(self.frames, "127.0.0.1", 0, stale_after_s=1.0)
        self.server.start()
        self.base_url = f"http://127.0.0.1:{self.server.bound_port}"

    def tearDown(self):
        self.server.close()

    def test_preview_page_is_served(self):
        with urlopen(self.base_url + "/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertIn("video.mjpg", response.read().decode("utf-8"))

    def test_health_reports_when_frame_is_available(self):
        with urlopen(self.base_url + "/health") as response:
            self.assertFalse(json.loads(response.read())["camera_ready"])

        self.frames.publish(b"fake-jpeg")
        with urlopen(self.base_url + "/health") as response:
            self.assertTrue(json.loads(response.read())["camera_ready"])

    def test_stream_sends_latest_frame(self):
        stream_result = []

        def read_stream():
            with urlopen(self.base_url + "/video.mjpg", timeout=2) as response:
                headers = []
                while True:
                    line = response.readline()
                    headers.append(line)
                    if line in (b"\r\n", b"\n", b""):
                        break
                content_length = next(
                    int(line.split(b":", 1)[1]) for line in headers if line.lower().startswith(b"content-length:")
                )
                stream_result.append(b"".join(headers) + response.read(content_length))

        client = threading.Thread(target=read_stream, daemon=True)
        client.start()
        time.sleep(0.05)
        self.frames.publish(b"demo-jpeg")
        client.join(timeout=1)

        self.assertFalse(client.is_alive())
        self.assertIn(b"Content-Type: image/jpeg", stream_result[0])
        self.assertIn(b"demo-jpeg", stream_result[0])


if __name__ == "__main__":
    unittest.main()
