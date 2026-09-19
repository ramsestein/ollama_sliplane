"""Tests de anonymizer.py (mapeos, regex y placeholders, sin cargar BERT)."""
import hashlib

from src import anonymizer


def test_map_bert_label():
    assert anonymizer._map_bert_label("B-FECHAS") == "DATE"
    assert anonymizer._map_bert_label("I-CALLE") == "LOCATION"
    assert anonymizer._map_bert_label("ANON") == "PHI"
    assert anonymizer._map_bert_label("B-DESCONOCIDO") == "OTHER"


def test_map_step2_label():
    assert anonymizer._map_step2_label("DATE") == "DATE"
    assert anonymizer._map_step2_label("PERSON") == "NAME"
    assert anonymizer._map_step2_label("DOCTOR") == "PROFESSIONAL"
    assert anonymizer._map_step2_label("RELATION") == "FAMILY"


def test_regex_detects_entities():
    anon = anonymizer.Anonymizer.__new__(anonymizer.Anonymizer)
    ents = anon._regex_detect(
        "Ingreso el 12/05/2024 a las 10:30 en Barcelona. "
        "Telefono: 600123456. Edad: 45 años. Dr. Garcia."
    )
    labels = {e["label"] for e in ents}
    assert "DATE" in labels
    assert "TIME" in labels
    assert "LOCATION" in labels
    assert "PHONE" in labels
    assert "AGE" in labels
    assert "PROFESSIONAL" in labels


def _make_anon(entities):
    anon = anonymizer.Anonymizer.__new__(anonymizer.Anonymizer)
    anon.text_to_ph = {}
    anon.ph_to_text = {}
    anon.counters = {}
    anon.detect = lambda text: entities
    return anon


def test_placeholder_roundtrip():
    text = "Maria vive en Barcelona"
    ents = [
        {"start": text.index("Maria"), "end": text.index("Maria") + 5,
         "label": "NAME", "text": "Maria"},
        {"start": text.index("Barcelona"), "end": text.index("Barcelona") + 9,
         "label": "LOCATION", "text": "Barcelona"},
    ]
    anon = _make_anon(ents)
    out = anon.anonymize(text)
    assert "Maria" not in out
    assert "Barcelona" not in out
    assert anon.deanonymize(out) == text


def test_deanonymize_longest_first():
    anon = _make_anon([])
    anon.ph_to_text = {"[NOMBRE_1]": "Ana", "[NOMBRE_10]": "Luis"}
    out = anon.deanonymize("[NOMBRE_10] y [NOMBRE_1]")
    assert out == "Luis y Ana"


def test_reset_clears_maps():
    anon = anonymizer.Anonymizer.__new__(anonymizer.Anonymizer)
    anon.text_to_ph = {"x": "[NOMBRE_1]"}
    anon.ph_to_text = {"[NOMBRE_1]": "x"}
    anon.counters = {"NOMBRE": 5}
    anon.reset()
    assert anon.text_to_ph == {}
    assert anon.ph_to_text == {}
    assert anon.counters == {}


def test_verify_model_hash(monkeypatch, tmp_path):
    weights = tmp_path / "pytorch_model.bin"
    weights.write_bytes(b"abc")
    expected = hashlib.sha256(b"abc").hexdigest()
    monkeypatch.setenv("BERT_MODEL_SHA256", expected)
    assert anonymizer.verify_model_hash(tmp_path) is True
    monkeypatch.setenv("BERT_MODEL_SHA256", "0" * 64)
    assert anonymizer.verify_model_hash(tmp_path) is False
