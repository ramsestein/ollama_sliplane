"""Tests de secure.py (cifrado AES-GCM con clave rotatoria)."""
import base64
import json

from src import secure


def test_roundtrip():
    secret = "clave-de-prueba"
    msg = b"hola mundo secreto"
    envelope = secure.encrypt(secret, msg)
    assert secure.decrypt(secret, envelope) == msg


def test_wrong_secret_fails():
    envelope = secure.encrypt("secreto-a", b"mensaje")
    try:
        secure.decrypt("secreto-b", envelope)
        assert False, "debería fallar con otro secreto"
    except Exception:
        pass


def test_tampered_ciphertext_fails():
    envelope = secure.encrypt("secreto", b"mensaje")
    ct = bytearray(base64.b64decode(envelope["ciphertext"]))
    ct[0] ^= 0xFF  # corrompemos un byte
    envelope["ciphertext"] = base64.b64encode(ct).decode("ascii")
    try:
        secure.decrypt("secreto", envelope)
        assert False, "debería fallar al manipular el ciphertext"
    except Exception:
        pass


def test_window_math():
    assert secure.current_window(0) == 0
    assert secure.current_window(299) == 0
    assert secure.current_window(300) == 1
    assert secure.current_window(301) == 1


def test_window_tolerance_previous():
    secret = "secreto"
    w = secure.current_window()
    envelope = secure.encrypt(secret, b"hola", window=w - 1)
    assert secure.decrypt(secret, envelope) == b"hola"


def test_window_tolerance_next():
    secret = "secreto"
    w = secure.current_window()
    envelope = secure.encrypt(secret, b"hola", window=w + 1)
    assert secure.decrypt(secret, envelope) == b"hola"


def test_auth_roundtrip():
    model = "qwen3:0.6b"
    bert = "PlanTL-GOB-ES/bsc-bio-ehr-es-carmen-anon"
    password = "clave"
    creds = b'{"user":"admin","password":"clave"}'
    env = secure.encrypt_auth(model, bert, password, creds)
    assert secure.decrypt_auth(model, bert, password, env) == creds


def test_auth_wrong_password_fails():
    env = secure.encrypt_auth("m", "bert", "clave", b"creds")
    try:
        secure.decrypt_auth("m", "bert", "otra", env)
        assert False, "debería fallar con otra contraseña"
    except Exception:
        pass


def test_auth_wrong_model_fails():
    env = secure.encrypt_auth("m1", "bert", "pw", b"creds")
    try:
        secure.decrypt_auth("m2", "bert", "pw", env)
        assert False, "debería fallar con otro modelo"
    except Exception:
        pass


def test_auth_wrong_bert_fails():
    env = secure.encrypt_auth("m", "bert1", "pw", b"creds")
    try:
        secure.decrypt_auth("m", "bert2", "pw", env)
        assert False, "debería fallar con otro BERT"
    except Exception:
        pass


def test_build_auth_envelope():
    env = secure.build_auth_envelope("m", "bert", "admin", "clave")
    creds = json.loads(secure.decrypt_auth("m", "bert", "clave", env).decode("utf-8"))
    assert creds == {"user": "admin", "password": "clave"}
