"""Zero-dependency local web server for V2X Nexus.

Run: python server.py
If scikit-learn is installed, the AI scheduler uses the synthetic-label random
forest. Without it, the explainable heuristic fallback is used.
"""
from __future__ import annotations
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from engine import run_experiment
from ai_model import model_description

ROOT = Path(__file__).resolve().parent
TRACE = ROOT / 'data' / 'sumo_trace.json'
MAX_REQUEST = 16 * 1024


class Handler(BaseHTTPRequestHandler):
    def _respond(self, status: int, payload: bytes, content_type: str):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: object):
        self._respond(status, json.dumps(obj, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            self._json(200, {
                'status':'ok',
                'traffic':'SUMO trace available' if TRACE.is_file() else 'synthetic traffic ready',
                'sumo_trace_available':TRACE.is_file(),
                'network':'simplified Python V2X network model (not ns-3)',
                'ai':model_description()
            })
            return
        if path == '/':
            file = ROOT / 'templates' / 'index.html'
        elif path.startswith('/static/'):
            file = (ROOT / path.lstrip('/')).resolve()
            if not file.is_relative_to((ROOT / 'static').resolve()):
                self._json(403, {'error':'Forbidden'}); return
        else:
            self._json(404, {'error':'Not found'}); return
        if not file.is_file():
            self._json(404, {'error':'Resource not found'});return
        content_type = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        if content_type.startswith(('text/', 'application/javascript')):
            content_type += '; charset=utf-8'
        self._respond(200, file.read_bytes(), content_type)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/run':
            self._json(404, {'error':'Not found'});return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not (0 < length <= MAX_REQUEST):
                self._json(413, {'error':'Request too large or empty'});return
            raw = json.loads(self.rfile.read(length))
            if not isinstance(raw,dict):
                raise ValueError('Send a JSON configuration object')
            output=run_experiment(raw, str(TRACE) if TRACE.is_file() else None)
            self._json(200,output)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            self._json(400,{'error':str(exc)})


def main():
    port=int(os.environ.get('PORT','5000'))
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'V2X Nexus ready: http://127.0.0.1:{port}', flush=True)
    print('Ctrl+C stops the server.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nServer stopped')
    finally:server.server_close()


if __name__=='__main__':
    main()
