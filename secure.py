"""Cifrado simétrico con rotación de clave por ventana de tiempo (5 min).

La clave efectiva se deriva del secreto compartido + la ventana de tiempo:
    key = HMAC-SHA256(secreto, "ollama-secure:{ventana}")

De este modo la clave cambia automáticamente cada 5 minutos. El cifrado es
AES-256-GCM (autenticado). Se tolera un desfase de reloj de +/- 1 ventana
(10 minutos) entre cliente y servidor.
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
    """Descifra tolerando un desfase de reloj de +/- 1 ventana (10 min)."""
    w = int(envelope["window"])
    nonce = _b64d(envelope["nonce"])
    ciphertext = _b64d(envelope["ciphertext"])
    last_error = None
    for candidate in (w, w - 1, w + 1):
        try:
            return AESGCM(_derive_key(secret, candidate)).decrypt(nonce, ciphertext, None)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise ValueError("no se pudo descifrar") from last_error
