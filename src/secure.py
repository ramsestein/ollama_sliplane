"""Symmetric encryption with time-window rotating keys (5 minutes).

Two independent layers (double encryption):

1. Message layer (`encrypt` / `decrypt`): the key is derived from the shared
   secret plus the time window:
       key = HMAC-SHA256(ENCRYPTION_SECRET, "ollama-secure:{window}")

2. Auth layer (`encrypt_auth` / `decrypt_auth`): the key is derived from the
   sum (SHA-256) of the model name, the BERT model name and the auth password,
   then folded into the time window:
       base = SHA-256(model | bert_model | auth_password)
       key  = HMAC-SHA256(base, "pukara-auth:{window}")

Both layers use AES-256-GCM (authenticated) and tolerate a clock skew of
+/- 1 window (10 minutes) between client and server.
"""
import base64
import hashlib
import hmac
import json
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


# ── Auth layer (double encryption) ────────────────────────────────────────
_AUTH_CTX = b"pukara-auth:"


def _auth_key_base(model, bert_model, password):
    """Sum (SHA-256) of model name + BERT model name + auth password."""
    material = "|".join([model or "", bert_model or "", password or ""])
    return hashlib.sha256(material.encode("utf-8")).digest()


def _derive_auth_key(model, bert_model, password, window):
    return hmac.new(
        _auth_key_base(model, bert_model, password),
        _AUTH_CTX + str(window).encode("ascii"),
        hashlib.sha256,
    ).digest()


def encrypt_auth(model, bert_model, password, plaintext: bytes, window=None) -> dict:
    """Encrypt credentials with the auth-layer key (double encryption)."""
    w = window if window is not None else current_window()
    key = _derive_auth_key(model, bert_model, password, w)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "window": w,
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
    }


def decrypt_auth(model, bert_model, password, envelope: dict) -> bytes:
    """Decrypt credentials; tolerates +/- 1 window of clock skew."""
    w = int(envelope["window"])
    nonce = _b64d(envelope["nonce"])
    ciphertext = _b64d(envelope["ciphertext"])
    last_error = None
    for candidate in (w, w - 1, w + 1):
        try:
            return AESGCM(
                _derive_auth_key(model, bert_model, password, candidate)
            ).decrypt(nonce, ciphertext, None)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise ValueError("could not decrypt auth") from last_error


def build_auth_envelope(model, bert_model, user, password):
    """Encrypt the credentials {user, password} with the auth-layer key."""
    creds = json.dumps({"user": user, "password": password}).encode("utf-8")
    return encrypt_auth(model, bert_model, password, creds)
