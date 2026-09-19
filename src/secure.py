"""Pukara protocol v2 — pre-shared-key authenticated encryption.

Direction-separated AES-256-GCM with HKDF-SHA256 key derivation, server-clock
freshness, per-request ids and a bounded, fail-closed replay cache.

Envelope (JSON; all byte fields are base64):

    {"v": 2, "ts": <epoch seconds>, "req_id": <16 bytes>, "nonce": <12 bytes>,
     "ciphertext": <AES-GCM ciphertext + tag>}

Key derivation (no slow KDF by design: the secret is a random 32-byte key, not
a human password):

    c2s = HKDF-SHA256(salt=None, info=b"pukara/v2/c2s", ikm=secret)
    s2c = HKDF-SHA256(salt=None, info=b"pukara/v2/s2c", ikm=secret)

AAD is a fixed-length canonical encoding (never string concatenation):

    b"\x02" + direction_byte + ts.to_bytes(8, "big") + req_id

where direction_byte is b"\x01" (client->server) or b"\x02" (server->client).
Any alteration of a header field invalidates the GCM tag.

Limitations (documented, not hidden — see docs/dev/adr-001-protocol.md):

* PSK: no forward secrecy. Anyone who learns ENCRYPTION_SECRET can decrypt
  recorded traffic.
* Traffic sizes and timings are not hidden (no padding).
"""
import base64
import hmac
import os
import threading
import time
from collections import OrderedDict
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VERSION = 2
_VERSION_BYTE = b"\x02"

DIR_C2S = b"pukara/v2/c2s"
DIR_S2C = b"pukara/v2/s2c"
_C2S_BYTE = b"\x01"
_S2C_BYTE = b"\x02"

NONCE_LEN = 12
REQ_ID_LEN = 16
KEY_LEN = 32
_TS_LEN = 8  # big-endian epoch seconds

MAX_SKEW = int(os.environ.get("MAX_SKEW", "120"))
# The replay cache must strictly outlive the acceptance window
# (2 * MAX_SKEW seconds wide), otherwise a message accepted at the earliest
# possible moment could be replayed at the latest acceptable moment.
_REPLAY_TTL_ENV = int(os.environ.get("REPLAY_TTL", "0") or 0)
REPLAY_TTL = _REPLAY_TTL_ENV if _REPLAY_TTL_ENV > 2 * MAX_SKEW else 2 * MAX_SKEW + 1
REPLAY_MAX_ENTRIES = int(os.environ.get("REPLAY_MAX_ENTRIES", "100000") or 100000)


class SecureError(Exception):
    """Base for all protocol-level failures.

    The message must never be sent to clients: the proxy maps every SecureError
    to a single generic response. It may be logged internally for audit.
    """


class InvalidSecretError(ValueError):
    """ENCRYPTION_SECRET is empty, invalid base64, or shorter than 32 bytes."""


def b64e(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def load_secret(value: str) -> bytes:
    """Validate and decode ENCRYPTION_SECRET (base64 of >= 32 random bytes)."""
    if not value:
        raise InvalidSecretError("ENCRYPTION_SECRET is empty")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise InvalidSecretError("ENCRYPTION_SECRET is not valid base64") from exc
    if len(raw) < 32:
        raise InvalidSecretError("ENCRYPTION_SECRET must decode to >= 32 bytes")
    return raw


def generate_secret() -> str:
    """Return a fresh random base64 ENCRYPTION_SECRET (32 bytes)."""
    return b64e(os.urandom(32))


def _hkdf(secret: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=KEY_LEN, salt=None, info=info
    ).derive(secret)


def _now() -> int:
    return int(time.time())


def _check_freshness(ts: int, now: int) -> None:
    if abs(now - ts) > MAX_SKEW:
        raise SecureError("timestamp outside MAX_SKEW")


def _aad(direction: bytes, ts: int, req_id: bytes) -> bytes:
    if ts < 0:
        raise SecureError("negative timestamp")
    return _VERSION_BYTE + direction + int(ts).to_bytes(_TS_LEN, "big") + req_id


def _envelope(ts: int, req_id: bytes, nonce: bytes, ciphertext: bytes) -> dict:
    return {
        "v": VERSION,
        "ts": ts,
        "req_id": b64e(req_id),
        "nonce": b64e(nonce),
        "ciphertext": b64e(ciphertext),
    }


def _parse(envelope: dict) -> tuple[int, int, bytes, bytes, bytes]:
    if not isinstance(envelope, dict):
        raise SecureError("envelope is not an object")
    try:
        version = int(envelope["v"])
        ts = int(envelope["ts"])
        req_id = b64d(str(envelope["req_id"]))
        nonce = b64d(str(envelope["nonce"]))
        ciphertext = b64d(str(envelope["ciphertext"]))
    except Exception as exc:  # noqa: BLE001
        raise SecureError("malformed envelope") from exc
    if len(req_id) != REQ_ID_LEN:
        raise SecureError("bad req_id length")
    if len(nonce) != NONCE_LEN:
        raise SecureError("bad nonce length")
    return version, ts, req_id, nonce, ciphertext


def encrypt_request(
    secret: bytes, plaintext: bytes, req_id: Optional[bytes] = None, ts: Optional[int] = None
) -> dict:
    """Encrypt a client->server request. Returns the v2 envelope."""
    if req_id is None:
        req_id = os.urandom(REQ_ID_LEN)
    if len(req_id) != REQ_ID_LEN:
        raise ValueError("req_id must be 16 bytes")
    ts = _now() if ts is None else int(ts)
    nonce = os.urandom(NONCE_LEN)
    key = _hkdf(secret, DIR_C2S)
    aad = _aad(_C2S_BYTE, ts, req_id)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return _envelope(ts, req_id, nonce, ciphertext)


def decrypt_request(
    secret: bytes, envelope: dict, now: Optional[int] = None
) -> tuple[bytes, bytes]:
    """Decrypt a client->server request. Returns (plaintext, req_id).

    Raises SecureError on any failure (tag, freshness, malformed envelope).
    """
    version, ts, req_id, nonce, ciphertext = _parse(envelope)
    if version != VERSION:
        raise SecureError("unsupported version")
    now = _now() if now is None else int(now)
    key = _hkdf(secret, DIR_C2S)
    aad = _aad(_C2S_BYTE, ts, req_id)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:  # noqa: BLE001
        raise SecureError("decryption failed") from exc
    _check_freshness(ts, now)
    return plaintext, req_id


def encrypt_response(
    secret: bytes, plaintext: bytes, req_id: bytes, ts: Optional[int] = None
) -> dict:
    """Encrypt a server->client response, bound to the request's req_id."""
    if len(req_id) != REQ_ID_LEN:
        raise ValueError("req_id must be 16 bytes")
    ts = _now() if ts is None else int(ts)
    nonce = os.urandom(NONCE_LEN)
    key = _hkdf(secret, DIR_S2C)
    aad = _aad(_S2C_BYTE, ts, req_id)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return _envelope(ts, req_id, nonce, ciphertext)


def decrypt_response(
    secret: bytes, envelope: dict, expected_req_id: bytes, now: Optional[int] = None
) -> bytes:
    """Decrypt a server->client response and verify it belongs to this request."""
    version, ts, req_id, nonce, ciphertext = _parse(envelope)
    if version != VERSION:
        raise SecureError("unsupported version")
    now = _now() if now is None else int(now)
    key = _hkdf(secret, DIR_S2C)
    aad = _aad(_S2C_BYTE, ts, req_id)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:  # noqa: BLE001
        raise SecureError("decryption failed") from exc
    _check_freshness(ts, now)
    if not hmac.compare_digest(req_id, expected_req_id):
        raise SecureError("response req_id mismatch")
    return plaintext


class ReplayCache:
    """Bounded, fail-closed cache of seen req_ids.

    check_and_store returns False for a fresh req_id (and stores it), True for
    a replay or when the cache is full (fail-closed).
    """

    def __init__(self, ttl: int = REPLAY_TTL, max_entries: int = REPLAY_MAX_ENTRIES):
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries = OrderedDict()  # req_id (bytes) -> expiry
        self._lock = threading.Lock()

    def check_and_store(self, req_id: bytes, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else float(now)
        with self._lock:
            # Entries are inserted in time order, so expired ones sit at the
            # front. Amortized O(1) prune.
            while self._entries:
                _key, expiry = next(iter(self._entries.items()))
                if expiry <= now:
                    del self._entries[_key]
                else:
                    break
            if req_id in self._entries:
                return True
            if len(self._entries) >= self.max_entries:
                return True  # fail-closed: refuse when we cannot remember
            self._entries[req_id] = now + self.ttl
            return False

    def __len__(self) -> int:
        return len(self._entries)
