"""Encrypted proxy in front of Ollama.

Exposes:
  GET  /health         -> unencrypted status (for health checks)
  POST /secure/request -> encrypted envelope {window, nonce, ciphertext} containing
                          an inner request {method, path, body}. It is forwarded to
                          Ollama and the response is returned encrypted.

Ollama listens only on 127.0.0.1:11434 (never exposed to the outside).

Protections on /secure/request:
  - IP allowlist (ALLOWED_IPS).
  - X-Forwarded-For is only trusted from known proxies (TRUSTED_PROXIES).
  - Per-IP rate limiting (RATE_LIMIT requests/minute).
  - Anti-replay: an exact ciphertext is accepted only once (nonce uniqueness).
  - Encrypted credentials (double encryption, see secure.py).
  - JSON audit log (AUDIT_LOG), never the request/response body.
"""
import hmac
import ipaddress
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import secure

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PORT = int(os.environ.get("PROXY_PORT", "8000"))
SECRET = os.environ.get("ENCRYPTION_SECRET", "")
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
ALLOWED_IPS = os.environ.get("ALLOWED_IPS", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "")
BERT_MODEL = os.environ.get("BERT_MODEL", "")
TRUSTED_PROXIES = os.environ.get("TRUSTED_PROXIES", "")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "0") or 0)  # req/min per IP; 0 = off
AUDIT_LOG = os.environ.get("AUDIT_LOG", "")


def _parse_allowed_ips(raw):
    nets = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                sys.stderr.write("[proxy] invalid IP/CIDR ignored: %s\n" % item)
    return nets


_ALLOWED_NETS = _parse_allowed_ips(ALLOWED_IPS)
_TRUSTED_NETS = _parse_allowed_ips(TRUSTED_PROXIES)


def _resolve_client_ip(peer, xff=None, real=None):
    """Resolve the real client IP, trusting X-Forwarded-For only from known proxies."""
    if _TRUSTED_NETS:
        try:
            peer_addr = ipaddress.ip_address(peer)
        except ValueError:
            peer_addr = None
        if peer_addr is not None and any(peer_addr in net for net in _TRUSTED_NETS):
            if xff:
                return xff.split(",")[0].strip()
            if real:
                return real.strip()
    return peer


def _client_ip(handler):
    return _resolve_client_ip(
        handler.client_address[0],
        handler.headers.get("X-Forwarded-For"),
        handler.headers.get("X-Real-IP"),
    )


def _ip_allowed(ip):
    if not _ALLOWED_NETS:
        return True  # no list configured => no restriction
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _ALLOWED_NETS)


def _auth_ok(auth_envelope):
    """Validate the encrypted credentials (auth layer of double encryption).

    The envelope can only be opened with a key derived from OLLAMA_MODEL +
    BERT_MODEL + AUTH_PASSWORD, so it fails unless all three match the server.
    """
    if not AUTH_USER and not AUTH_PASSWORD:
        return True  # no credentials configured => no restriction
    if not isinstance(auth_envelope, dict):
        return False
    try:
        creds = json.loads(
            secure.decrypt_auth(OLLAMA_MODEL, BERT_MODEL, AUTH_PASSWORD, auth_envelope)
            .decode("utf-8")
        )
    except Exception:  # noqa: BLE001
        return False
    return (
        hmac.compare_digest(str(creds.get("user", "")), AUTH_USER)
        and hmac.compare_digest(str(creds.get("password", "")), AUTH_PASSWORD)
    )


# ── Rate limiting, anti-replay and audit ───────────────────────────────────
_RATE_WINDOW = 60.0
_rate_lock = threading.Lock()
_rate_hits = {}   # ip -> list of timestamps


def _rate_limited(ip):
    """True if `ip` exceeded RATE_LIMIT requests in the last minute."""
    if RATE_LIMIT <= 0:
        return False
    now = time.time()
    with _rate_lock:
        stamps = _rate_hits.setdefault(ip, [])
        stamps[:] = [t for t in stamps if now - t < _RATE_WINDOW]
        if len(stamps) >= RATE_LIMIT:
            return True
        stamps.append(now)
        return False


_REPLAY_TTL = 3 * secure.WINDOW_SECONDS
_seen_lock = threading.Lock()
_seen = {}   # message ciphertext -> expiry timestamp


def _is_replay(ciphertext):
    """True if this exact ciphertext was already processed (same nonce => replay)."""
    now = time.time()
    with _seen_lock:
        for key in list(_seen):
            if _seen[key] <= now:
                del _seen[key]
        if ciphertext in _seen:
            return True
        _seen[ciphertext] = now + _REPLAY_TTL
        return False


_audit_lock = threading.Lock()


def _audit(client_ip, method, path, status):
    """Append one JSON line per request to AUDIT_LOG (never the body)."""
    if not AUDIT_LOG:
        return
    try:
        line = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip": client_ip,
            "method": method,
            "path": path,
            "status": status,
        })
        with _audit_lock:
            with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError:
        pass


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
        req_path = self.path.rstrip("/")
        client_ip = _client_ip(self)

        if req_path != "/secure/request":
            self._json(404, {"error": "not found"})
            return

        if not _ip_allowed(client_ip):
            _audit(client_ip, "POST", req_path, 403)
            self._json(403, {"error": "ip not allowed"})
            return

        if _rate_limited(client_ip):
            _audit(client_ip, "POST", req_path, 429)
            self._json(429, {"error": "rate limit exceeded"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            envelope = json.loads(self.rfile.read(length))
        except Exception:  # noqa: BLE001
            _audit(client_ip, "POST", req_path, 400)
            self._json(400, {"error": "bad request"})
            return

        auth_envelope = envelope.get("auth") if isinstance(envelope, dict) else None
        if not _auth_ok(auth_envelope):
            _audit(client_ip, "POST", req_path, 401)
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="ollama"')
            self.end_headers()
            return

        try:
            inner = json.loads(secure.decrypt(SECRET, envelope).decode("utf-8"))
        except Exception:  # noqa: BLE001
            _audit(client_ip, "POST", req_path, 400)
            self._json(400, {"error": "bad request"})
            return

        ciphertext = envelope.get("ciphertext") if isinstance(envelope, dict) else None
        if isinstance(ciphertext, str) and _is_replay(ciphertext):
            _audit(client_ip, "POST", req_path, 409)
            self._json(409, {"error": "replayed request"})
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
        _audit(client_ip, method, path, status)
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
