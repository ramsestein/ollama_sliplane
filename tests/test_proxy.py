"""Tests de proxy.py (autenticación y lista blanca de IPs)."""
import base64
import ipaddress

from src import proxy


def test_parse_allowed_ips():
    nets = proxy._parse_allowed_ips("1.2.3.0/24, 5.6.7.8")
    assert len(nets) == 2


def test_parse_allowed_ips_empty():
    assert proxy._parse_allowed_ips("") == []


def test_auth_ok(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "admin")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "secret")
    token = base64.b64encode(b"admin:secret").decode("ascii")
    assert proxy._auth_ok({"Authorization": "Basic " + token}) is True
    assert proxy._auth_ok({}) is False


def test_auth_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(proxy, "AUTH_USER", "")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "")
    assert proxy._auth_ok({}) is True


def test_ip_allowed(monkeypatch):
    monkeypatch.setattr(proxy, "_ALLOWED_NETS", [ipaddress.ip_network("1.2.3.0/24")])
    assert proxy._ip_allowed("1.2.3.10") is True
    assert proxy._ip_allowed("5.6.7.8") is False
