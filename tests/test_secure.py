"""Tests de secure.py (protocolo v2)."""
import base64

import pytest

from src import secure

SECRET_B64 = base64.b64encode(b"\x00" * 32).decode("ascii")
SECRET = secure.load_secret(SECRET_B64)
REQ_ID = b"\x01" * secure.REQ_ID_LEN


def _enc(plaintext=b"hola", req_id=REQ_ID, ts=1_700_000_000):
    return secure.encrypt_request(SECRET, plaintext, req_id=req_id, ts=ts)


# ── Baselines ─────────────────────────────────────────────────────────────
def test_roundtrip_request():
    env = _enc(b"mensaje secreto")
    plaintext, req_id = secure.decrypt_request(SECRET, env, now=1_700_000_000)
    assert plaintext == b"mensaje secreto"
    assert req_id == REQ_ID


def test_roundtrip_response():
    env = secure.encrypt_response(SECRET, b"respuesta", REQ_ID, ts=1_700_000_000)
    assert secure.decrypt_response(SECRET, env, REQ_ID, now=1_700_000_000) == b"respuesta"


def test_wrong_secret_fails():
    env = _enc()
    other = secure.load_secret(base64.b64encode(b"\x01" * 32).decode("ascii"))
    with pytest.raises(secure.SecureError):
        secure.decrypt_request(other, env, now=1_700_000_000)


def test_tampered_ciphertext_fails():
    env = _enc()
    ct = bytearray(base64.b64decode(env["ciphertext"]))
    ct[0] ^= 0xFF
    env["ciphertext"] = base64.b64encode(ct).decode("ascii")
    with pytest.raises(secure.SecureError):
        secure.decrypt_request(SECRET, env, now=1_700_000_000)


# ── Header tampering ──────────────────────────────────────────────────────
@pytest.mark.parametrize("field,mutate", [
    ("v", lambda v: 3),
    ("ts", lambda v: v + 1),
    ("req_id", lambda v: base64.b64encode(b"\x02" * secure.REQ_ID_LEN).decode("ascii")),
    ("nonce", lambda v: base64.b64encode(b"\x03" * secure.NONCE_LEN).decode("ascii")),
])
def test_header_tampering_fails(field, mutate):
    env = _enc()
    env[field] = mutate(env[field])
    with pytest.raises(secure.SecureError):
        secure.decrypt_request(SECRET, env, now=1_700_000_000)


# ── Freshness (compared against the server clock) ─────────────────────────
def test_old_timestamp_rejected():
    env = _enc(ts=1_700_000_000)
    with pytest.raises(secure.SecureError):
        secure.decrypt_request(SECRET, env, now=1_700_000_000 + secure.MAX_SKEW + 1)


def test_future_timestamp_rejected():
    env = _enc(ts=1_700_000_000)
    with pytest.raises(secure.SecureError):
        secure.decrypt_request(SECRET, env, now=1_700_000_000 - secure.MAX_SKEW - 1)


# ── Reflection and response binding ───────────────────────────────────────
def test_reflection_request_as_response_rejected():
    env = _enc(b"peticion")
    with pytest.raises(secure.SecureError):
        secure.decrypt_response(SECRET, env, REQ_ID, now=1_700_000_000)


def test_response_with_foreign_req_id_rejected():
    env = secure.encrypt_response(SECRET, b"respuesta", REQ_ID, ts=1_700_000_000)
    foreign = b"\x09" * secure.REQ_ID_LEN
    with pytest.raises(secure.SecureError):
        secure.decrypt_response(SECRET, env, foreign, now=1_700_000_000)


# ── Secret validation ─────────────────────────────────────────────────────
def test_short_secret_rejected():
    with pytest.raises(secure.InvalidSecretError):
        secure.load_secret(base64.b64encode(b"corto").decode("ascii"))


def test_non_base64_secret_rejected():
    with pytest.raises(secure.InvalidSecretError):
        secure.load_secret("!!!no-es-base64!!!")


def test_empty_secret_rejected():
    with pytest.raises(secure.InvalidSecretError):
        secure.load_secret("")


def test_generate_secret_is_valid():
    assert len(secure.load_secret(secure.generate_secret())) == 32


# ── Replay cache ──────────────────────────────────────────────────────────
def test_replay_within_ttl_rejected():
    cache = secure.ReplayCache(ttl=300, max_entries=10)
    assert cache.check_and_store(REQ_ID, now=1000.0) is False
    assert cache.check_and_store(REQ_ID, now=1000.0) is True


def test_replay_outside_ttl_accepted():
    cache = secure.ReplayCache(ttl=300, max_entries=10)
    assert cache.check_and_store(REQ_ID, now=1000.0) is False
    assert cache.check_and_store(REQ_ID, now=1300.0 + 1) is False  # expired


def test_replay_cache_fail_closed_when_full():
    cache = secure.ReplayCache(ttl=300, max_entries=2)
    assert cache.check_and_store(b"\x01" * 16, now=1000.0) is False
    assert cache.check_and_store(b"\x02" * 16, now=1000.0) is False
    assert cache.check_and_store(b"\x03" * 16, now=1000.0) is True  # fail-closed


def test_replay_ttl_strictly_exceeds_window():
    assert secure.REPLAY_TTL > 2 * secure.MAX_SKEW


def test_replay_rejected_at_window_edge():
    cache = secure.ReplayCache(ttl=2 * secure.MAX_SKEW + 1, max_entries=10)
    assert cache.check_and_store(REQ_ID, now=1000.0) is False
    # 2*MAX_SKEW later is the last moment a message accepted at t=1000-MAX_SKEW
    # could still pass freshness; the entry must still be cached.
    assert cache.check_and_store(REQ_ID, now=1000.0 + 2 * secure.MAX_SKEW) is True


# ── KAT: key derivation and AAD ───────────────────────────────────────────
def test_hkdf_kat():
    ikm = bytes(range(32))
    assert secure._hkdf(ikm, secure.DIR_C2S).hex() == (
        "9231393928b4e4301bc3e6ac5f4ed0227fb98aebdc4837ed1b261ff97ac4471e"
    )
    assert secure._hkdf(ikm, secure.DIR_S2C).hex() == (
        "daeedae32f6b3f0423e245d97da6c6c4464279bb80e24fde9d97b62d7e47e2c4"
    )


def test_aad_kat():
    req_id = b"\x10" * 16
    aad = secure._aad(b"\x01", 0x0102030405060708, req_id)
    assert aad == b"\x02\x01" + (0x0102030405060708).to_bytes(8, "big") + req_id


# ── Auth layer must be gone ───────────────────────────────────────────────
def test_auth_layer_absent():
    for name in ("encrypt_auth", "decrypt_auth", "build_auth_envelope"):
        assert not hasattr(secure, name)
