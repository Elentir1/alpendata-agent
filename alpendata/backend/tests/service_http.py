"""Real loopback HTTP transport for synthetic DAV and Office provider responses."""

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter


@contextmanager
def service_http(respond):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            request = {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
            received.append(request)
            status, headers, data = respond(request)
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PATCH = do_PUT = do_PROPFIND = do_REPORT = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True

    class LoopbackAdapter(HTTPAdapter):
        def send(self, request, **kwargs):
            copied = request.copy()
            copied.url = f"http://127.0.0.1:{server.server_port}" + urlsplit(request.url).path
            return super().send(copied, **kwargs)

    session = requests.Session()
    session.mount("https://", LoopbackAdapter())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield session, received
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
