"""A loopback HTTP provider; only its model responses are synthetic."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter


@contextmanager
def model_http(handler):
    received, destinations = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append({"body": payload, "headers": dict(self.headers), "path": self.path})
            status, body, headers = handler(payload)
            content = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Oversized and rejected responses are deliberately closed early.
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True

    class LoopbackAdapter(HTTPAdapter):
        local_origin = f"http://127.0.0.1:{server.server_port}"

        def send(self, request, **kwargs):
            destinations.append(request.url)
            local = request.copy()
            local.url = self.local_origin + urlsplit(request.url).path
            return super().send(local, **kwargs)

    session = requests.Session()
    session.mount("https://", LoopbackAdapter())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield session, received, destinations
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def completion(body, *, content="Synthetic answer"):
    return {
        "id": "synthetic-completion",
        "object": "chat.completion",
        "created": 1,
        "model": body["model"],
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
