"""Temporary HTTPS tunnel from this tablet to Debian's package servers only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import select
import socket

ALLOWED = {'deb.debian.org', 'security.debian.org'}

class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_CONNECT(self):
        host, _, port = self.path.rpartition(':')
        if self.client_address[0] != '192.168.77.2' or host not in ALLOWED or port != '443':
            self.send_error(403)
            return
        try:
            upstream = socket.create_connection((host, 443), timeout=20)
        except OSError:
            self.send_error(502)
            return
        self.send_response(200, 'Connection established')
        self.end_headers()
        try:
            sockets = (self.connection, upstream)
            while True:
                ready, _, _ = select.select(sockets, [], [], 60)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:
            pass
        finally:
            upstream.close()
            self.close_connection = True

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

print('Debian package tunnel listening on USB address 192.168.77.1:3142', flush=True)
ThreadingHTTPServer(('192.168.77.1', 3142), Proxy).serve_forever()
