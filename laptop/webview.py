"""Tiny web server for the game page: static files, live video, and game state.

    /         web/index.html (and the other files in web/)
    /video    camera as MJPEG, for an <img>
    /events   game state as Server-Sent Events, one JSON per frame

game.py calls publish() once per frame; every open page gets the newest frame
and state. Only the standard library is used.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).parent / "web"
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class Hub:
    """Newest frame + state, handed from the game loop to the page connections."""

    def __init__(self):
        self.cond = threading.Condition()
        self.seq = 0
        self.jpeg = b""
        self.state = "{}"

    def publish(self, jpeg, state):
        with self.cond:
            self.seq += 1
            self.jpeg, self.state = jpeg, json.dumps(state)
            self.cond.notify_all()

    def wait(self, last_seq):
        """Block until there is something newer than last_seq (or 1 s passes)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=1.0)
            return self.seq, self.jpeg, self.state


def make_handler(hub):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path == "/video":
                    self.stream(b"multipart/x-mixed-replace; boundary=frame", self.video_part)
                elif path == "/events":
                    self.stream(b"text/event-stream", self.event_part)
                else:
                    self.static(path)
            except (BrokenPipeError, ConnectionResetError):
                pass  # page closed or reloaded

        def static(self, path):
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (WEB_DIR / name).resolve()
            if file.parent != WEB_DIR.resolve() or not file.is_file():
                self.send_error(404)
                return
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(file.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def stream(self, content_type, part):
            self.send_response(200)
            self.send_header("Content-Type", content_type.decode())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = 0
            while True:
                new_seq, jpeg, state = hub.wait(seq)
                if new_seq != seq:
                    seq = new_seq
                    self.wfile.write(part(jpeg, state))
                    self.wfile.flush()

        @staticmethod
        def video_part(jpeg, state):
            return (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")

        @staticmethod
        def event_part(jpeg, state):
            return f"data: {state}\n\n".encode()

        def log_message(self, *args):
            pass  # keep the console for game output

    return Handler


def start(port):
    """Serve in a background thread. Returns the Hub to publish() into."""
    hub = Hub()
    server = ThreadingHTTPServer(("", port), make_handler(hub))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return hub
