"""Symmetric encryption with a time-window rotating key (5 minutes).

The effective key is derived from the shared secret plus the time window:
    key = HMAC-SHA256(secret, "ollama-secure:{window}")

This makes the key rotate automatically every 5 minutes. Encryption is
AES-256-GCM (authenticated). A clock skew of +/- 1 window (10 minutes)
between client and server is tolerated.
"""
import base64
import hashlib
import hmac
import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

WINDOW_SECONDS = 300
_NONCE_LEN = 12
_DERIVE_CTX = b"ollama-secure:"


def current_window(ts=None):
    """Ventana de tiempo actual (cambia cada 300 segundos)."""
    ts = ts if ts is not None else int(time.time())
    return int(ts // WINDOW_SECONDS)


def _derive_key(secret: str, window: int) -> bytes:
    return hmac.new(
        secret.encode("utf-8"),
        _DERIVE_CTX + str(window).encode("ascii"),
        hashlib.sha256,
    ).digest()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def encrypt(secret: str, plaintext: bytes, window=None) -> dict:
    """Devuelve el sobre {window, nonce, ciphertext}; ciphertext incluye el tag GCM."""
    w = window if window is not None else current_window()
    key = _derive_key(secret, w)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "window": w,
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
    }


def decrypt(secret: str, envelope: dict) -> bytes:
    """Decrypt tolerating a clock skew of +/- 1 window (10 minutes)."""
    w = int(envelope["window"])
    nonce = _b64d(envelope["nonce"])
    ciphertext = _b64d(envelope["ciphertext"])
    last_error = None
    for candidate in (w, w - 1, w + 1):
        try:
            return AESGCM(_derive_key(secret, candidate)).decrypt(nonce, ciphertext, None)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise ValueError("could not decrypt") from last_error
