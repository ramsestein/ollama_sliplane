"""Encrypted proxy in front of Ollama.

Exposes:
  GET  /health         -> unencrypted status (for health checks)
  POST /secure/request -> encrypted envelope {window, nonce, ciphertext} containing
                          an inner request {method, path, body}. It is forwarded to
                          Ollama and the response is returned encrypted.

Ollama listens only on 127.0.0.1:11434 (never exposed to the outside).
"""
import base64
import hmac
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import secure

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PORT = int(os.environ.get("PROXY_PORT", "8000"))
SECRET = os.environ.get("ENCRYPTION_SECRET", "")
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
ALLOWED_IPS = os.environ.get("ALLOWED_IPS", "")


def _parse_allowed_ips(raw):
    nets = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                sys.stderr.write("[proxy] invalid IP in ALLOWED_IPS: %s\n" % item)
    return nets


_ALLOWED_NETS = _parse_allowed_ips(ALLOWED_IPS)


def _client_ip(handler):
    xff = handler.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    real = handler.headers.get("X-Real-IP")
    if real:
        return real.strip()
    return handler.client_address[0]


def _ip_allowed(ip):
    if not _ALLOWED_NETS:
        return True  # no list configured => no restriction
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _ALLOWED_NETS)


def _auth_ok(headers):
    if not AUTH_USER and not AUTH_PASSWORD:
        return True  # no credentials configured => no restriction
    auth = headers.get("Authorization", "")
    expected = base64.b64encode(
        ("%s:%s" % (AUTH_USER, AUTH_PASSWORD)).encode("utf-8")
    ).decode("ascii")
    provided = auth[6:] if auth.startswith("Basic ") else ""
    return hmac.compare_digest(provided, expected)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] %s\n" % (fmt % args))

    def _json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._json(200, {"ok": True, "window": secure.current_window()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/secure/request":
            self._json(404, {"error": "not found"})
            return

        client_ip = _client_ip(self)
        if not _ip_allowed(client_ip):
            self._json(403, {"error": "ip not allowed"})
            return
        if not _auth_ok(self.headers):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="ollama"')
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            envelope = json.loads(self.rfile.read(length))
            inner = json.loads(secure.decrypt(SECRET, envelope).decode("utf-8"))
        except Exception:  # noqa: BLE001
            self._json(400, {"error": "bad request"})
            return

        method = str(inner.get("method", "GET")).upper()
        path = str(inner.get("path", "/"))
        body = inner.get("body")

        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            OLLAMA_URL + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            status = 502
            raw = json.dumps({"error": str(exc)})

        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw

        response_inner = {"status": status, "body": parsed}
        self._json(200, secure.encrypt(SECRET, json.dumps(response_inner).encode("utf-8")))


def main():
    if not SECRET:
        sys.stderr.write("ERROR: ENCRYPTION_SECRET no está definida\n")
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("Proxy seguro escuchando en 0.0.0.0:%d\n" % PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
