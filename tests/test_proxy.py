"""Tests de proxy.py (protocolo v2)."""
import ipaddress

from src import proxy, secure


def test_parse_allowed_ips():
    nets = proxy._parse_allowed_ips("1.2.3.0/24, 5.6.7.8")
    assert len(nets) == 2


def test_parse_allowed_ips_empty():
    assert proxy._parse_allowed_ips("") == []


def test_auth_ok(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    inner = {"credentials": {"user": "admin", "password": "secret"}}
    assert proxy._auth_ok(inner) is True


def test_auth_ok_wrong_password(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    inner = {"credentials": {"user": "admin", "password": "wrong"}}
    assert proxy._auth_ok(inner) is False


def test_auth_ok_missing_credentials(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    assert proxy._auth_ok({}) is False
    assert proxy._auth_ok(None) is False


def test_auth_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "")
    assert proxy._auth_ok(None) is True


def test_ip_allowed(monkeypatch):
    monkeypatch.setattr(proxy, "_ALLOWED_NETS", [ipaddress.ip_network("1.2.3.0/24")])
    assert proxy._ip_allowed("1.2.3.10") is True
    assert proxy._ip_allowed("5.6.7.8") is False


def test_resolve_client_ip_trusted_proxy(monkeypatch):
    monkeypatch.setattr(proxy, "_TRUSTED_NETS", [ipaddress.ip_network("10.0.0.0/8")])
    # peer is a known proxy => honor X-Forwarded-For
    assert proxy._resolve_client_ip("10.0.0.1", "9.9.9.9", None) == "9.9.9.9"
    # peer is NOT a known proxy => ignore X-Forwarded-For
    assert proxy._resolve_client_ip("8.8.8.8", "9.9.9.9", None) == "8.8.8.8"


def test_resolve_client_ip_no_trusted(monkeypatch):
    monkeypatch.setattr(proxy, "_TRUSTED_NETS", [])
    assert proxy._resolve_client_ip("8.8.8.8", "9.9.9.9", None) == "8.8.8.8"


def test_rate_limited(monkeypatch):
    monkeypatch.setattr(proxy, "RATE_LIMIT", 2)
    proxy._rate_hits.clear()
    assert proxy._rate_limited("1.1.1.1") is False
    assert proxy._rate_limited("1.1.1.1") is False
    assert proxy._rate_limited("1.1.1.1") is True


def test_replay_cache_used():
    assert isinstance(proxy._replay, secure.ReplayCache)


def test_generic_denial_is_stable():
    assert proxy._GENERIC_DENIAL == {"error": "unauthorized"}


def test_validate_path():
    assert proxy._validate_path("/api/chat") is True
    assert proxy._validate_path("@evil.com/x") is False
    assert proxy._validate_path("//evil.com/x") is False
    assert proxy._validate_path("/api\\chat") is False
    assert proxy._validate_path("/api/chat?x=1") is False
    assert proxy._validate_path("/api/ch\0at") is False
    assert proxy._validate_path("relative") is False


def test_route_allowed_inference():
    assert proxy._route_allowed("POST", "/api/chat") is True
    assert proxy._route_allowed("GET", "/api/tags") is True
    assert proxy._route_allowed("POST", "/v1/chat/completions") is True


def test_route_allowed_management_denied(monkeypatch):
    monkeypatch.setattr(proxy, "ALLOW_MANAGEMENT", False)
    assert proxy._route_allowed("POST", "/api/pull") is False
    assert proxy._route_allowed("DELETE", "/api/delete") is False


def test_route_allowed_management_flag(monkeypatch):
    monkeypatch.setattr(proxy, "ALLOW_MANAGEMENT", True)
    assert proxy._route_allowed("POST", "/api/pull") is True


def test_upstream_url():
    assert proxy._upstream_url("/api/chat") == proxy.OLLAMA_URL + "/api/chat"


def test_upstream_url_rejects_host_trick():
    try:
        proxy._upstream_url("//evil.com/x")
        assert False, "debería rechazar rutas con //"
    except ValueError:
        pass


def test_rate_limited_bounded(monkeypatch):
    monkeypatch.setattr(proxy, "RATE_LIMIT", 1)
    monkeypatch.setattr(proxy, "MAX_RATE_IPS", 2)
    proxy._rate_hits.clear()
    assert proxy._rate_limited("1.1.1.1") is False
    assert proxy._rate_limited("2.2.2.2") is False
    assert proxy._rate_limited("3.3.3.3") is True  # fail-closed al llenarse
