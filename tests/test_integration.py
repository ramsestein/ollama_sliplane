"""Integration tests: proxy <-> client against a fake Ollama (Phase 5)."""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src import client, proxy, secure

SECRET_B64 = base64.b64encode(b"0" * 32).decode("ascii")
SECRET_BYTES = secure.load_secret(SECRET_B64)


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _reply(self, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path == "/api/chat":
            self._reply({"message": {"role": "assistant", "content": "hola fake"},
                         "done": True})
        elif self.path == "/v1/chat/completions":
            self._reply({"choices": [{"message": {"role": "assistant",
                                                  "content": "hola fake"}}]})
        elif self.path == "/api/generate":
            data = json.dumps({"error": "upstream failure"}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._reply({"ok": True})

    def do_GET(self):
        self._reply({"models": []})


def _start(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture()
def fake_ollama():
    server = _start(FakeOllamaHandler)
    yield "http://127.0.0.1:%d" % server.server_port
    server.shutdown()


@pytest.fixture()
def proxy_server(fake_ollama, monkeypatch):
    monkeypatch.setattr(proxy, "SECRET", SECRET_B64)
    monkeypatch.setattr(proxy, "OLLAMA_URL", fake_ollama)
    monkeypatch.setattr(proxy, "_OLLAMA", urllib.parse.urlsplit(fake_ollama))
    monkeypatch.setattr(proxy, "AUTH_USER", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "pw")
    monkeypatch.setattr(proxy, "OLLAMA_MODEL", "m1")
    monkeypatch.setattr(proxy, "BERT_MODEL", "bert1")
    monkeypatch.setattr(proxy, "_ALLOWED_NETS", [])
    monkeypatch.setattr(proxy, "RATE_LIMIT", 0)
    monkeypatch.setattr(proxy, "_replay", secure.ReplayCache())
    server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_port
    server.shutdown()


def _config(**overrides):
    cfg = {"model": "m1", "bert_model": "bert1", "user": "admin", "password": "pw"}
    cfg.update(overrides)
    return cfg


def _raw_envelope(path="/api/chat", body=None):
    inner = {"method": "POST", "path": path, "body": body, "config": _config()}
    return secure.encrypt_request(SECRET_BYTES, json.dumps(inner).encode("utf-8"))


def test_chat_roundtrip(proxy_server):
    result = client.secure_request(
        SECRET_B64, proxy_server, "POST", "/api/chat",
        {"model": "m1", "messages": [{"role": "user", "content": "hola"}]},
        _config(),
    )
    assert result["status"] == 200
    assert result["body"]["message"]["content"] == "hola fake"


def test_health_ok_only(proxy_server):
    with urllib.request.urlopen(proxy_server + "/health", timeout=10) as resp:
        assert resp.status == 200
        assert json.loads(resp.read()) == {"ok": True}


def test_wrong_config_denied(proxy_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.secure_request(
            SECRET_B64, proxy_server, "POST", "/api/chat",
            {"model": "m1", "messages": []}, _config(password="wrong"),
        )
    assert exc.value.code == 401
    assert json.loads(exc.value.read()) == {"error": "unauthorized"}


def test_replay_rejected(proxy_server):
    envelope = _raw_envelope()
    data = json.dumps(envelope).encode("utf-8")
    url = proxy_server + "/secure/request"
    req1 = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req1, timeout=10) as resp:
        assert resp.status == 200
    req2 = urllib.request.Request(url, data=data, method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req2, timeout=10)
    assert exc.value.code == 401


def test_management_route_denied(proxy_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.secure_request(
            SECRET_B64, proxy_server, "POST", "/api/pull",
            {"name": "modelo"}, _config(),
        )
    assert exc.value.code == 403


def test_oversized_body_rejected(proxy_server, monkeypatch):
    monkeypatch.setattr(proxy, "MAX_BODY_BYTES", 10)
    envelope = _raw_envelope()
    data = json.dumps(envelope).encode("utf-8")
    req = urllib.request.Request(proxy_server + "/secure/request", data=data,
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 413


def test_ip_not_allowed(proxy_server, monkeypatch):
    import ipaddress
    monkeypatch.setattr(proxy, "_ALLOWED_NETS", [ipaddress.ip_network("10.0.0.0/8")])
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.secure_request(SECRET_B64, proxy_server, "POST", "/api/chat",
                              {"model": "m1"}, _config())
    assert exc.value.code == 403


def test_rate_limited_429(proxy_server, monkeypatch):
    monkeypatch.setattr(proxy, "RATE_LIMIT", 1)
    client.secure_request(SECRET_B64, proxy_server, "POST", "/api/chat",
                          {"model": "m1"}, _config())
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.secure_request(SECRET_B64, proxy_server, "POST", "/api/chat",
                              {"model": "m1"}, _config())
    assert exc.value.code == 429


def test_bad_request_body(proxy_server):
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=b"not-json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_invalid_secret(proxy_server, monkeypatch):
    monkeypatch.setattr(proxy, "SECRET", "!!!invalid-base64!!!")
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.secure_request(SECRET_B64, proxy_server, "POST", "/api/chat",
                              {"model": "m1"}, _config())
    assert exc.value.code == 401


def test_tampered_ciphertext_rejected(proxy_server):
    envelope = _raw_envelope()
    ct = bytearray(base64.b64decode(envelope["ciphertext"]))
    ct[0] ^= 0xFF
    envelope["ciphertext"] = base64.b64encode(bytes(ct)).decode("ascii")
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=json.dumps(envelope).encode("utf-8"),
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 401


def test_bad_inner_json(proxy_server):
    envelope = secure.encrypt_request(SECRET_BYTES, b"not-json")
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=json.dumps(envelope).encode("utf-8"),
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_missing_config_denied(proxy_server):
    inner = {"method": "POST", "path": "/api/chat", "body": {"model": "m1"}}
    envelope = secure.encrypt_request(SECRET_BYTES, json.dumps(inner).encode("utf-8"))
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=json.dumps(envelope).encode("utf-8"),
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 401


def test_invalid_path_rejected(proxy_server):
    inner = {"method": "POST", "path": "@evil.com/x", "body": {},
             "config": _config()}
    envelope = secure.encrypt_request(SECRET_BYTES, json.dumps(inner).encode("utf-8"))
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=json.dumps(envelope).encode("utf-8"),
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_upstream_http_error_wrapped(proxy_server):
    result = client.secure_request(
        SECRET_B64, proxy_server, "POST", "/api/generate",
        {"model": "m1", "prompt": "x"}, _config(),
    )
    assert result["status"] == 500


def test_non_dict_inner_json(proxy_server):
    inner = ["not", "a", "dict"]
    envelope = secure.encrypt_request(SECRET_BYTES, json.dumps(inner).encode("utf-8"))
    req = urllib.request.Request(proxy_server + "/secure/request",
                                 data=json.dumps(envelope).encode("utf-8"),
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_audit_log_written(proxy_server, tmp_path):
    audit_file = tmp_path / "audit.jsonl"
    proxy.AUDIT_LOG = str(audit_file)
    try:
        client.secure_request(SECRET_B64, proxy_server, "POST", "/api/chat",
                              {"model": "m1", "messages": []}, _config())
    finally:
        proxy.AUDIT_LOG = ""

    lines = audit_file.read_text(encoding="utf-8").splitlines()
    assert lines
    entry = json.loads(lines[-1])
    assert "req_id" in entry
    assert "size" in entry
