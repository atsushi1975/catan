# wsgi.py - PythonAnywhere (WSGI) entry point.
#
# PythonAnywhere cannot run a long-lived server process, so the same app is
# exposed as a WSGI application here. All logic lives in app_core.
#
# Setup on PythonAnywhere (free plan):
#   1. Upload/clone this repo, e.g. to /home/<user>/catan
#   2. Web tab -> Add a new web app -> Manual configuration -> Python 3.10+
#   3. Set "Source code" to  /home/<user>/catan
#   4. Set "Working directory" to /home/<user>/catan
#   5. Edit the WSGI configuration file and make it import this module:
#         import sys
#         sys.path.insert(0, '/home/<user>/catan')
#         from wsgi import application
#   6. (Recommended) Force a SINGLE worker so the in-memory room is shared:
#         Web tab -> "Force HTTPS" etc. and in the WSGI file / config,
#         run the app single-process. On free PythonAnywhere the web app is
#         already one process - keep it that way.
#
# NOTE: the room lives in memory. A process restart (incl. the free plan's
# daily restart) clears any game in progress.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app_core
from app_core import route_get, route_post

# Reset the room once when this module is first imported by the worker.
app_core.ensure_started()

# ---------------------------------------------------------------------------
# WSGI application
#   Written with the standard library only (no Flask needed) so it runs on any
#   PythonAnywhere plan. Compatible with the "Manual configuration" WSGI file.
# ---------------------------------------------------------------------------
from urllib.parse import parse_qs


def _client_ip(environ):
    # PythonAnywhere terminates TLS and proxies to the worker: the real client
    # shows up in X-Forwarded-For. We only use this for the /env debug gate, so
    # default to a non-local value when it is missing.
    fwd = environ.get('HTTP_X_FORWARDED_FOR', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return environ.get('REMOTE_ADDR', '')


def application(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    path = environ.get('PATH_INFO', '/') or '/'
    query = parse_qs(environ.get('QUERY_STRING', ''))
    ip = _client_ip(environ)

    if method == 'GET':
        status, ctype, body = route_get(path, query, ip)
        status_line = {
            200: '200 OK',
            404: '404 Not Found',
        }.get(status, '%d Unknown' % status)
        headers = [
            ('Content-Type', ctype),
            ('Content-Length', str(len(body))),
            ('Cache-Control', 'no-cache, no-store, must-revalidate'),
        ]
        start_response(status_line, headers)
        return [body]

    if method == 'POST':
        try:
            length = int(environ.get('CONTENT_LENGTH') or 0)
        except ValueError:
            length = 0
        raw = environ['wsgi.input'].read(length).decode('utf-8') if length else '{}'
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        res = route_post(payload, query, ip)
        body = json.dumps(res).encode('utf-8')
        start_response('200 OK', [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Content-Length', str(len(body))),
        ])
        return [body]

    start_response('405 Method Not Allowed', [('Content-Type', 'text/plain')])
    return [b'Method Not Allowed']


# Some hosts look for a specific name; expose a few aliases.
app = application
