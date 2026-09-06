"""Loopback HTTP transport for the simulator, not a production/5G server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from .session import CommandError, Session


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON value")


def make_server(port=8765, session=None):
    """Bind IPv4 loopback only. Port 0 selects a free port for integration tests."""
    game = session if session is not None else Session()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass

        def send_json(self, status, payload):
            body = json.dumps(payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                self.send_json(200, {"status": "ok", "simulation_only": True, "protocol_version": 1})
            elif path == "/state":
                self.send_json(200, game.state())
            else:
                self.send_json(404, {"error": "not_found"})

        def do_POST(self):
            if urlsplit(self.path).path != "/commands":
                self.send_json(404, {"error": "not_found"})
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise CommandError("content_type", "Use application/json", 415)
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    raise CommandError("content_length", "One Content-Length is required", 400)
                try:
                    length = int(lengths[0])
                except ValueError:
                    raise CommandError("content_length", "Invalid Content-Length")
                if not 1 <= length <= 8192:
                    raise CommandError("payload_size", "Body must be 1-8192 bytes", 413)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise CommandError("invalid_json", "Incomplete request body")
                try:
                    command = json.loads(raw, object_pairs_hook=_unique_object,
                                         parse_constant=_reject_constant)
                except (ValueError, UnicodeError, RecursionError):
                    raise CommandError("invalid_json", "Body must be valid JSON with unique fields")
                reply = game.submit(command)
                self.send_json(200, reply)
            except CommandError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message, "state": game.state()})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
