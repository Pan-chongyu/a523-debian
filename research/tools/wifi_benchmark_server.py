"""Bounded local WLAN transfer endpoint; serves random bytes, never workspace files."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading

parser = argparse.ArgumentParser()
parser.add_argument('--bind', required=True)
parser.add_argument('--client', required=True)
parser.add_argument('--seconds', type=int, default=900)
args = parser.parse_args()
assert args.bind == '10.0.2.40' and args.client == '10.0.2.139'
assert 1 <= args.seconds <= 900
payload = os.urandom(8 * 1024 * 1024)
digest = hashlib.sha256(payload).hexdigest()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def allowed(self):
        if self.client_address[0] != args.client:
            self.send_error(403)
            return False
        self.connection.settimeout(45)
        return True

    def do_GET(self):
        if not self.allowed():
            return
        if self.path != '/data':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('X-TZX-SHA256', digest)
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self.allowed():
            return
        if self.path != '/upload' or self.headers.get('Content-Length') != str(len(payload)):
            self.send_error(400)
            return
        data = self.rfile.read(len(payload))
        if len(data) != len(payload) or hashlib.sha256(data).hexdigest() != self.headers.get('X-TZX-SHA256'):
            self.send_error(422)
            return
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, fmt, *values):
        print(fmt % values, flush=True)


server = ThreadingHTTPServer((args.bind, 18765), Handler)
threading.Timer(args.seconds, server.shutdown).start()
print('BOUNDED_WLAN_BENCHMARK_SERVER_READY', flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
