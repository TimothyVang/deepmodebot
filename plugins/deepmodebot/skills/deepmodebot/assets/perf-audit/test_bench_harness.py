import http.server
import json
import sys
import threading
import unittest
from io import StringIO
from unittest.mock import patch

from bench_harness import main


class _OkHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class BenchHarnessTests(unittest.TestCase):
    def test_http_bench_against_local_server(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            port = server.server_address[1]
            buf = StringIO()
            with patch("sys.stdout", buf):
                rc = main(["http", "--url", f"http://127.0.0.1:{port}/health", "--concurrency", "2", "--duration", "0.3", "--warmup", "0.05", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertGreater(data["requests"], 0)
            self.assertEqual(data["errors"], 0)
        finally:
            server.shutdown()
            server.server_close()

    def test_cmd_bench_runs_cleanly(self):
        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["cmd", "--runs", "3", "--warmup", "1", "--json", "--", sys.executable, "-c", "print('ok')"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["runs"], 3)
        self.assertEqual(data["errors"], 0)


if __name__ == "__main__":
    unittest.main()
