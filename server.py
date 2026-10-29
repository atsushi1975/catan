# server.py - local / Codespaces HTTP server.
#
# Thin adapter over app_core (the game + routing live there). Run this for
# local play and for Codespaces:
#
#     python3 server.py
#
# For the PythonAnywhere deployment use wsgi.py instead.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import app_core
from app_core import route_get, route_post

PORT = int(os.environ.get("CATAN_PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        status, ctype, body = route_get(parsed.path, qs, self.client_address[0])
        self._send(status, ctype, body)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        qs = parse_qs(parsed.query)
        res = route_post(payload, qs, self.client_address[0])
        body = json.dumps(res).encode()
        self._send(200, "application/json; charset=utf-8", body)

    def _send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--port', '-p', type=int, default=None)
    p.add_argument('--host', default='0.0.0.0')
    args = p.parse_args()
    port = args.port if args.port is not None else PORT
    app_core.ensure_started()
    httpd = ThreadingHTTPServer((args.host, port), Handler)
    print(f"Catan server running at http://{args.host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
