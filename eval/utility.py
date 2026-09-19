"""Utility-preservation evaluation, no LLM involved (Phase 4.4).

Measures what pseudonymisation deterministically destroys or breaks:

1. Exact round-trip: `deanonymize(anonymize(x)) == x` byte-for-byte. Any failure
   is a bug, not a metric.
2. Placeholder robustness: deterministic perturbations applied to anonymized
   text (mimicking what an LLM does to placeholders when answering) and the
   percentage restored correctly per perturbation type.

Runs with the regex-only detector; BERT mode is TODO until the model is local.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from eval import common

ADVERSARIAL = [
    "Texto que ya contiene [NOMBRE_1] literal.",
    "Corchetes anidados [[NOMBRE_1]] y [NOMBRE_10].",
    "Unicode: María, Núria, Mercè, ç, ñ, ü.",
    "Entidades solapadas: Hospital Clínic de Barcelona.",
    "Número 600123456 y fecha 12/05/2024.",
    "Apellido epónimo: enfermedad de Crohn y Parkinson.",
    "Entidad pegada a puntuación: (Juan García),",
]

PERTURBATIONS = {
    "uppercase": lambda s: s.upper(),
    "bold_markers": lambda s: s.replace("[", "**[", 1).replace("]", "]**", 1),
    "lost_brackets": lambda s: s.replace("[", "").replace("]", ""),
    "inner_space": lambda s: s.replace("_", " _"),
    "label_translated": lambda s: s.replace("NOMBRE", "NAME").replace("FECHA", "DATE"),
    "plural_suffix": lambda s: s.replace("]", "s]"),
    "split_by_newline": lambda s: s.replace("]", "]\n"),
}


def _regex_anon():
    anon = common.anonymizer.Anonymizer.__new__(common.anonymizer.Anonymizer)
    anon.reset()
    anon.detect = anon._regex_detect
    return anon


def roundtrip(texts):
    anon = _regex_anon()
    failures = []
    for text in texts:
        anon.reset()
        anonymized = anon.anonymize(text)
        restored = anon.deanonymize(anonymized)
        if restored != text:
            failures.append({"text": text, "anonymized": anonymized,
                             "restored": restored})
    return failures


def robustness(texts):
    anon = _regex_anon()
    results = {}
    for name, perturb in PERTURBATIONS.items():
        ok = 0
        total = 0
        for text in texts:
            anon.reset()
            anonymized = anon.anonymize(text)
            if not any(ph in anonymized for ph in anon.ph_to_text):
                continue  # no placeholders to perturb
            perturbed = perturb(anonymized)
            restored = anon.deanonymize(perturbed)
            total += 1
            if restored == text:
                ok += 1
        results[name] = {
            "restored": ok,
            "total": total,
            "rate": round(ok / total, 4) if total else 0.0,
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Utility-preservation eval")
    parser.add_argument("--corpus", default="data/meddocan/corpus")
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--out", default="eval/results/utility.json")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    texts = list(ADVERSARIAL)
    seen = 0
    for ann in sorted((corpus / "dev" / "brat").glob("*.ann")):
        txt = ann.with_suffix(".txt")
        if txt.exists():
            texts.append(common.read_text(txt))
            seen += 1
            if seen >= args.sample:
                break

    failures = roundtrip(texts)
    rob = robustness(texts)

    result = {
        "script": "eval/utility.py",
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "code_revision": _git(),
        "roundtrip": {
            "texts": len(texts),
            "failures": len(failures),
            "rate": round(1 - len(failures) / len(texts), 4) if texts else 0.0,
            "examples": failures[:10],
        },
        "robustness": rob,
        "notes": [
            "Round-trip failures are bugs, not metrics.",
            "Perturbations mimic deterministic LLM edits to placeholders.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("[utility] roundtrip failures=%d, robustness=%s"
          % (len(failures), {k: v["rate"] for k, v in rob.items()}))
    return 0


def _git():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=common.ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
