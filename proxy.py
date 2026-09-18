"""Proxy cifrado delante de Ollama.

Expone:
  GET  /health         -> estado sin cifrar (para healthchecks)
  POST /secure/request -> sobre cifrado {window, nonce, ciphertext} que contiene
                          una petición interna {method, path, body}. Se reenvía a
                          Ollama y la respuesta se devuelve cifrada.

Ollama queda escuchando solo en 127.0.0.1:11434 (no accesible desde fuera).
"""
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
