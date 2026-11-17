"""Synthetic localhost-only catalog for real browser/client acceptance.

No credentials or live customer data. Every API response has a fresh nonce.
Stop with Ctrl-C; this server is never started by installing the plugin.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), FixtureHandler)
        self.lock = threading.Lock()
        self.api_hits = 0
        self.last_nonce = None


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/":
            payload = (
                b'<!doctype html><title>Synthetic catalog</title><h1>Products</h1><pre id="items"></pre>'
                b'<script>fetch("/api/products").then(r=>r.json()).then(data=>'
                b'document.querySelector("#items").textContent=JSON.stringify(data));</script>'
            )
            mime = "text/html; charset=utf-8"
        elif self.path == "/api/products":
            with self.server.lock:
                self.server.api_hits += 1
                self.server.last_nonce = secrets.token_hex(16)
                payload = json.dumps({"items": [{"id": 1, "name": "sample product"}],
                                      "nonce": self.server.last_nonce}).encode()
            mime = "application/json"
        elif self.path == "/stats":
            with self.server.lock:
                payload = json.dumps({"api_hits": self.server.api_hits, "last_nonce": self.server.last_nonce}).encode()
            mime = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with FixtureServer(args.port) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
