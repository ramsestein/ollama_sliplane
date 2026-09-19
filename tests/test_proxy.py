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
