"""Tests de los helpers de anonimización de local_ollama.py."""
import os

# Evita que local_ollama.py salga por falta de ENCRYPTION_SECRET al importar.
os.environ.setdefault("ENCRYPTION_SECRET", "test-secret")

import local_ollama as lo  # noqa: E402


class StubAnon:
    def __init__(self):
        self.map = {}
        self.n = 0

    def anonymize(self, text):
        self.n += 1
        self.map[f"X{self.n}"] = text
        return f"X{self.n}"

    def deanonymize(self, text):
        for ph, orig in self.map.items():
            text = text.replace(ph, orig)
        return text


def test_anonymize_and_deanonymize_messages():
    anon = StubAnon()
    req = {"model": "m", "messages": [{"role": "user", "content": "hola Maria"}]}
    lo._anonymize_body(anon, req)
    assert req["messages"][0]["content"] == "X1"

    resp = {"message": {"content": "adios X1"}}
    lo._deanonymize_body(anon, resp)
    assert resp["message"]["content"] == "adios hola Maria"


def test_generate_prompt_anonymized():
    anon = StubAnon()
    req = {"prompt": "di hola"}
    lo._anonymize_body(anon, req)
    assert req["prompt"] == "X1"


def test_v1_choices_deanonymized():
    anon = StubAnon()
    anon.anonymize("hola")  # X1 -> hola
    resp = {"choices": [{"message": {"content": "X1"}}]}
    lo._deanonymize_body(anon, resp)
    assert resp["choices"][0]["message"]["content"] == "hola"
