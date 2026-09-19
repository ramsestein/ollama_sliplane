"""Encrypted proxy in front of Ollama (protocol v2).

Exposes:
  GET  /health         -> {"ok": true} for health checks
  POST /secure/request -> encrypted envelope {v, ts, req_id, nonce, ciphertext}
                          containing an inner request {method, path, body,
                          credentials}. It is forwarded to Ollama and the
                          response is returned encrypted and bound to req_id.

Ollama listens only on 127.0.0.1:11434 (never exposed to the outside).

Protections on /secure/request:
  - IP allowlist (ALLOWED_IPS).
  - X-Forwarded-For is only trusted from known proxies (TRUSTED_PROXIES).
  - Per-IP rate limiting (RATE_LIMIT requests/minute).
  - Anti-replay of req_id, checked after tag verification, with a bounded
    fail-closed cache.
  - Credentials (user/password) travel inside the encrypted payload and are
    compared with hmac.compare_digest. Possession of the PSK already
    authenticates; credentials are for audit/segregation, not a second factor.
  - Single generic error response for tag/freshness/replay/credential failures;
    the real cause goes only to the audit log.
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
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import secure

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PORT = int(os.environ.get("PROXY_PORT", "8000"))
SECRET = os.environ.get("ENCRYPTION_SECRET", "")
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
ALLOWED_IPS = os.environ.get("ALLOWED_IPS", "")
TRUSTED_PROXIES = os.environ.get("TRUSTED_PROXIES", "")
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "0") or 0)  # req/min per IP; 0 = off
AUDIT_LOG = os.environ.get("AUDIT_LOG", "")
ALLOW_MANAGEMENT = os.environ.get("ALLOW_MANAGEMENT", "0") == "1"
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(10 * 1024 * 1024)) or 0)
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "600") or 600)
MAX_RATE_IPS = int(os.environ.get("MAX_RATE_IPS", "100000") or 100000)
STRICT = os.environ.get("STRICT", "0") == "1"

# The generic, oracle-free error returned for tag/freshness/replay/credential
# failures. The real cause is only written to the audit log.
_GENERIC_DENIAL = {"error": "unauthorized"}

# Explicit (method, path) allowlist: inference and listing only. Model
# management routes are denied unless ALLOW_MANAGEMENT=1.
_ALLOWED_METHOD_PATHS = {
    ("GET", "/api/tags"),
    ("GET", "/api/version"),
    ("POST", "/api/show"),
    ("POST", "/api/chat"),
    ("POST", "/api/generate"),
    ("POST", "/api/embed"),
    ("POST", "/api/embeddings"),
    ("GET", "/v1/models"),
    ("POST", "/v1/chat/completions"),
    ("POST", "/v1/completions"),
    ("POST", "/v1/embeddings"),
}

_MANAGEMENT_PATHS = {
    "/api/pull", "/api/delete", "/api/create", "/api/copy", "/api/push",
    "/api/blobs",
}

_OLLAMA = urllib.parse.urlsplit(OLLAMA_URL)


def _validate_path(path):
    """Reject paths that cannot be a safe upstream path."""
    if not isinstance(path, str):
        return False
    if not path.startswith("/"):
        return False
    if "//" in path or "@" in path or "\\" in path:
        return False
    if "?" in path or "#" in path:
        return False
    if any(ord(ch) < 32 for ch in path):
        return False
    return True


def _route_allowed(method, path):
    if (method, path) in _ALLOWED_METHOD_PATHS:
        return True
    if ALLOW_MANAGEMENT and path in _MANAGEMENT_PATHS:
        return True
    return False


def _upstream_url(path):
    """Build the upstream URL from OLLAMA_URL and a validated path.

    The path is always inserted as a path component (never a netloc), so the
    result cannot resolve to a different host.
    """
    if not _validate_path(path):
        raise ValueError("invalid upstream path")
    target = urllib.parse.urlunsplit((_OLLAMA.scheme, _OLLAMA.netloc, path, "", ""))
    check = urllib.parse.urlsplit(target)
    if (check.scheme, check.netloc) != (_OLLAMA.scheme, _OLLAMA.netloc):
        raise ValueError("upstream URL escaped OLLAMA_URL")
    return target


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


def _auth_ok(inner):
    """Validate plaintext credentials inside the decrypted payload.

    Possession of the PSK already authenticates; these credentials exist for
    audit and tenant segregation, not as a second factor. Compared in constant
    time.
    """
    if not AUTH_USER and not AUTH_PASSWORD:
        return True  # no credentials configured => no restriction
    if not isinstance(inner, dict):
        return False
    creds = inner.get("credentials")
    if not isinstance(creds, dict):
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
        stamps = _rate_hits.get(ip)
        if stamps is None:
            if len(_rate_hits) >= MAX_RATE_IPS:
                return True  # fail-closed: cannot track more distinct IPs
            stamps = []
            _rate_hits[ip] = stamps
        stamps[:] = [t for t in stamps if now - t < _RATE_WINDOW]
        if len(stamps) >= RATE_LIMIT:
            return True
        stamps.append(now)
        return False


_replay = secure.ReplayCache()

_audit_lock = threading.Lock()


def _audit(client_ip, method, path, status, req_id=None, reason=None, size=None):
    """Append one JSON line per request to AUDIT_LOG (never the body)."""
    if not AUDIT_LOG:
        return
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ip": client_ip,
        "method": method,
        "path": path,
        "status": status,
    }
    if req_id is not None:
        entry["req_id"] = req_id
    if reason is not None:
        entry["reason"] = reason
    if size is not None:
        entry["size"] = size
    try:
        line = json.dumps(entry)
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
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        req_path = self.path.rstrip("/")
        client_ip = _client_ip(self)

        if req_path != "/secure/request":
            self._json(404, {"error": "not found"})
            return

        if not _ip_allowed(client_ip):
            _audit(client_ip, "POST", req_path, 403, reason="ip_not_allowed")
            self._json(403, {"error": "ip not allowed"})
            return

        if _rate_limited(client_ip):
            _audit(client_ip, "POST", req_path, 429, reason="rate_limited")
            self._json(429, {"error": "rate limit exceeded"})
            return

        length = 0
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:  # noqa: BLE001
            _audit(client_ip, "POST", req_path, 400, reason="bad_content_length")
            self._json(400, {"error": "bad request"})
            return

        if length < 0 or length > MAX_BODY_BYTES:
            _audit(client_ip, "POST", req_path, 413, reason="body_too_large",
                   size=length)
            self._json(413, {"error": "payload too large"})
            return

        try:
            raw_body = self.rfile.read(length)
            envelope = json.loads(raw_body)
        except Exception:  # noqa: BLE001
            _audit(client_ip, "POST", req_path, 400, reason="bad_request", size=length)
            self._json(400, {"error": "bad request"})
            return

        try:
            secret = secure.load_secret(SECRET)
        except secure.InvalidSecretError:
            _audit(client_ip, "POST", req_path, 401, reason="invalid_secret")
            self._json(401, _GENERIC_DENIAL)
            return

        # Tag + freshness verification (authenticated headers only).
        try:
            plaintext, req_id = secure.decrypt_request(secret, envelope)
        except secure.SecureError:
            _audit(client_ip, "POST", req_path, 401, reason="decrypt_failure")
            self._json(401, _GENERIC_DENIAL)
            return

        # Anti-replay, checked after the tag has been verified.
        if _replay.check_and_store(req_id):
            _audit(client_ip, "POST", req_path, 401, reason="replay",
                   req_id=secure.b64e(req_id))
            self._json(401, _GENERIC_DENIAL)
            return

        try:
            inner = json.loads(plaintext.decode("utf-8"))
        except Exception:  # noqa: BLE001
            _audit(client_ip, "POST", req_path, 400, reason="bad_inner_json",
                   req_id=secure.b64e(req_id))
            self._json(400, {"error": "bad request"})
            return

        if not isinstance(inner, dict):
            _audit(client_ip, "POST", req_path, 400, reason="bad_inner_json",
                   req_id=secure.b64e(req_id))
            self._json(400, {"error": "bad request"})
            return

        if not _auth_ok(inner):
            _audit(client_ip, "POST", req_path, 401, reason="bad_credentials",
                   req_id=secure.b64e(req_id))
            self._json(401, _GENERIC_DENIAL)
            return

        method = str(inner.get("method", "GET")).upper()
        path = str(inner.get("path", "/"))

        if not _validate_path(path):
            _audit(client_ip, "POST", req_path, 400, reason="invalid_path",
                   req_id=secure.b64e(req_id))
            self._json(400, {"error": "bad request"})
            return

        if not _route_allowed(method, path):
            _audit(client_ip, "POST", req_path, 403, reason="route_denied",
                   req_id=secure.b64e(req_id))
            self._json(403, {"error": "forbidden"})
            return

        body = inner.get("body")

        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        try:
            upstream_url = _upstream_url(path)
        except ValueError:
            _audit(client_ip, method, path, 400, reason="invalid_path",
                   req_id=secure.b64e(req_id))
            self._json(400, {"error": "bad request"})
            return

        req = urllib.request.Request(
            upstream_url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
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
        _audit(client_ip, method, path, status, req_id=secure.b64e(req_id),
               size=length)
        response_envelope = secure.encrypt_response(
            secret, json.dumps(response_inner).encode("utf-8"), req_id
        )
        self._json(200, response_envelope)


def main():
    try:
        secure.load_secret(SECRET)
    except secure.InvalidSecretError as exc:
        sys.stderr.write("ERROR: ENCRYPTION_SECRET inválida: %s\n" % exc)
        sys.exit(1)

    warnings = []
    if not ALLOWED_IPS:
        warnings.append("ALLOWED_IPS no está definida: se aceptan todas las IPs")
    if not AUTH_USER and not AUTH_PASSWORD:
        warnings.append("AUTH_USER/AUTH_PASSWORD no definidas: credenciales desactivadas")
    for msg in warnings:
        sys.stderr.write("[proxy] ADVERTENCIA: %s\n" % msg)
    if STRICT and warnings:
        sys.stderr.write("[proxy] STRICT=1: configuración insegura, no se arranca\n")
        sys.exit(1)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("Proxy seguro escuchando en 0.0.0.0:%d\n" % PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
