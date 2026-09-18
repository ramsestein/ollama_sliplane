#!/usr/bin/env python3
"""Servidor local que simula Ollama y reenvía al proxy remoto cifrado.

Ejecuta:  python local_ollama.py

Queda escuchando en http://127.0.0.1:11434 (el puerto por defecto de Ollama).
Cualquier herramienta que hable con Ollama local (VS Code + extensiones,
Open WebUI, el CLI `ollama`, etc.) puede usar el modelo alojado en Sliplane
como si fuera local.
"""
import argparse
import base64
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import secure

DEFAULT_REMOTE = "https://ollama-sliplane.sliplane.app"
STREAMING_PATHS = {"/api/chat", "/api/generate", "/v1/chat/completions", "/v1/completions"}


def read_env(key):
    if os.environ.get(key):
        return os.environ[key]
    try:
        with open(".env", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1]
    except OSError:
        pass
    return ""


REMOTE_URL = (read_env("REMOTE_URL") or DEFAULT_REMOTE).rstrip("/")
SECRET = read_env("ENCRYPTION_SECRET")
AUTH_USER = read_env("AUTH_USER")
AUTH_PASSWORD = read_env("AUTH_PASSWORD")
LOCAL_PORT = int(read_env("LOCAL_PORT") or "11434")
DEFAULT_MODEL = read_env("OLLAMA_MODEL") or "gemma3:270m"

if __name__ == "__main__" and not SECRET:
    sys.stderr.write("Falta ENCRYPTION_SECRET en .env\n")
    sys.exit(1)


def _auth_header():
    if AUTH_USER and AUTH_PASSWORD:
        token = base64.b64encode(
            ("%s:%s" % (AUTH_USER, AUTH_PASSWORD)).encode("utf-8")
        ).decode("ascii")
        return "Basic " + token
    return None


def forward(method, path, body=None):
    """Envía una petición al proxy remoto (cifrada) y devuelve (status, body)."""
    inner = {"method": method, "path": path, "body": body}
    envelope = secure.encrypt(SECRET, json.dumps(inner).encode("utf-8"))
    data = json.dumps(envelope).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    auth = _auth_header()
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(
        REMOTE_URL + "/secure/request", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            resp_envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")

    result = json.loads(secure.decrypt(SECRET, resp_envelope).decode("utf-8"))
    return result.get("status", 500), result.get("body")


def _ensure_chat_capability(obj):
    """Algunos modelos base (p. ej. gemma3:270m) se reportan solo como
    'completion'. Añadimos 'chat' para que la extensión de Ollama para VS Code
    permita seleccionarlo como modelo de chat.

    No inyectamos 'tools': si el modelo no las soporta (p. ej. toda la familia
    gemma3), la extensión las enviaría igualmente y Ollama respondería
    HTTP 400 'does not support tools'."""
    if isinstance(obj, dict):
        caps = obj.get("capabilities")
        if caps is None:
            obj["capabilities"] = ["chat", "completion"]
        elif isinstance(caps, list):
            for cap in ("chat", "completion"):
                if cap not in caps:
                    caps.append(cap)
    return obj


# ── Capa de anonimización (opcional: BERT + regex en local) ────────────────
try:
    from anonymizer import get_anonymizer
except Exception:  # noqa: BLE001
    get_anonymizer = None

_ANON_LOCK = threading.Lock()


def _anonymize_body(anon, body):
    """Anonimiza los campos de texto de una petición (in-place)."""
    if not isinstance(body, dict):
        return body
    messages = body.get("messages")
    if isinstance(messages, list):
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                m["content"] = anon.anonymize(m["content"])
    if isinstance(body.get("prompt"), str):
        body["prompt"] = anon.anonymize(body["prompt"])
    return body


def _deanonymize_body(anon, body):
    """Restaura los placeholders de una respuesta."""
    if not isinstance(body, dict):
        return body
    message = body.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        message["content"] = anon.deanonymize(message["content"])
    choices = body.get("choices")
    if isinstance(choices, list):
        for c in choices:
            if isinstance(c, dict) and isinstance(c.get("message"), dict) \
                    and isinstance(c["message"].get("content"), str):
                c["message"]["content"] = anon.deanonymize(c["message"]["content"])
    if isinstance(body.get("response"), str):
        body["response"] = anon.deanonymize(body["response"])
    return body


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[local] %s\n" % (fmt % args))

    def _send(self, code, data, content_type="application/json"):
        if isinstance(data, (dict, list)):
            data = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            data = data.encode("utf-8")
        elif data is None:
            data = b""
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # El cliente (p. ej. VS Code) cerró la conexión antes de terminar.
            # Es inofensivo y no debe imprimir un traceback.
            pass

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            self._send(200, "Ollama is running", "text/plain")
            return
        if self.path == "/api/version":
            self._send(200, {"version": "0.34.2"})
            return
        if self.path == "/api/tags":
            status, body = forward("GET", "/api/tags")
            if isinstance(body, dict) and isinstance(body.get("models"), list):
                for m in body["models"]:
                    _ensure_chat_capability(m)
            self._send(status, body)
            return
        if self.path == "/v1/models":
            _, tags_body = forward("GET", "/api/tags")
            models = []
            if isinstance(tags_body, dict) and isinstance(tags_body.get("models"), list):
                for m in tags_body["models"]:
                    models.append(
                        {
                            "id": m.get("name", DEFAULT_MODEL),
                            "object": "model",
                            "created": 0,
                            "owned_by": "ollama",
                        }
                    )
            self._send(200, {"object": "list", "data": models})
            return
        status, body = forward("GET", self.path)
        self._send(status, body)

    def do_POST(self):
        raw = self._read_body()
        try:
            req_body = json.loads(raw) if raw else {}
        except ValueError:
            req_body = raw.decode("utf-8", "replace")

        if self.path == "/api/show":
            status, body = forward("POST", "/api/show", req_body)
            _ensure_chat_capability(body)
            self._send(status, body)
            return

        want_stream = False
        if isinstance(req_body, dict) and self.path in STREAMING_PATHS:
            want_stream = bool(req_body.get("stream", False))
            req_body = dict(req_body)
            req_body["stream"] = False

        use_anon = self.path in STREAMING_PATHS and get_anonymizer is not None
        anon = None
        if use_anon:
            _ANON_LOCK.acquire()
            try:
                anon = get_anonymizer()
                if anon is not None:
                    anon.reset()
                    _anonymize_body(anon, req_body)
                status, body = forward("POST", self.path, req_body)
                if anon is not None:
                    body = _deanonymize_body(anon, body)
            finally:
                _ANON_LOCK.release()
        else:
            status, body = forward("POST", self.path, req_body)

        if want_stream and self.path.startswith("/v1/"):
            # SSE para el endpoint compatible con OpenAI
            payload = "data: " + json.dumps(body) + "\n\ndata: [DONE]\n\n"
            self._send(status, payload, "text/event-stream")
            return
        if want_stream and isinstance(body, dict):
            # NDJSON de una sola línea (válido para clientes de streaming)
            self._send(status, json.dumps(body) + "\n", "application/x-ndjson")
            return

        self._send(status, body)


def main():
    parser = argparse.ArgumentParser(description="Ollama local -> proxy remoto cifrado")
    parser.add_argument("--remote", help="URL del proxy remoto (defecto: la de .env)")
    parser.add_argument("--port", type=int, help="Puerto local (defecto 11434)")
    args = parser.parse_args()

    global REMOTE_URL, LOCAL_PORT
    if args.remote:
        REMOTE_URL = args.remote.rstrip("/")
    if args.port:
        LOCAL_PORT = args.port

    server = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), Handler)
    sys.stderr.write(
        "Ollama local en http://127.0.0.1:%d -> %s\n" % (LOCAL_PORT, REMOTE_URL)
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
