"""Cost benchmark: anonymization and encryption latency + client memory (4.5).

Declares hardware. Runs with the regex-only detector (no model needed).
"""
from __future__ import annotations

import argparse
import datetime
import json
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

from eval import common
from src import secure


def _regex_anon():
    anon = common.anonymizer.Anonymizer.__new__(common.anonymizer.Anonymizer)
    anon.reset()
    anon.detect = anon._regex_detect
    return anon


def load_sample(corpus: Path, n: int) -> list[str]:
    texts = []
    for ann in sorted((corpus / "dev" / "brat").glob("*.ann")):
        txt = ann.with_suffix(".txt")
        if txt.exists():
            texts.append(common.read_text(txt))
            if len(texts) >= n:
                break
    return texts


def measure_anonymization(texts, repeats=3):
    anon = _regex_anon()
    latencies = []
    for _ in range(repeats):
        for text in texts:
            anon.reset()
            t0 = time.perf_counter()
            anon.anonymize(text)
            latencies.append(time.perf_counter() - t0)
    latencies.sort()
    return latencies


def measure_encryption(secret_bytes, sizes=(64, 1024, 4096, 16384), repeats=200):
    rows = []
    for size in sizes:
        payload = b"x" * size
        lat = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            env = secure.encrypt_request(secret_bytes, payload)
            secure.decrypt_request(secret_bytes, env)
            lat.append(time.perf_counter() - t0)
        lat.sort()
        rows.append({
            "size_bytes": size,
            "p50_ms": round(statistics.median(lat) * 1000, 4),
            "p95_ms": round(lat[int(0.95 * (len(lat) - 1))] * 1000, 4),
        })
    return rows


def measure_memory(texts):
    anon = _regex_anon()
    tracemalloc.start()
    for text in texts:
        anon.reset()
        anon.anonymize(text)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost benchmark")
    parser.add_argument("--corpus", default="data/meddocan/corpus")
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--out", default="eval/results/cost.json")
    args = parser.parse_args()

    texts = load_sample(Path(args.corpus), args.sample)
    if not texts:
        print("[cost] No hay documentos para medir", file=sys.stderr)
        return 2

    anon_lat = measure_anonymization(texts)
    secret_bytes = secure.load_secret(secure.generate_secret())
    enc_rows = measure_encryption(secret_bytes)
    peak_mem = measure_memory(texts)

    result = {
        "script": "eval/cost.py",
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "code_revision": _git(),
        "hardware": {
            "cpu": platform.processor() or platform.machine(),
            "platform": platform.platform(),
        },
        "anonymization_latency_ms": {
            "documents": len(texts),
            "p50": round(statistics.median(anon_lat) * 1000, 4),
            "p95": round(anon_lat[int(0.95 * (len(anon_lat) - 1))] * 1000, 4),
        },
        "encryption_ms": enc_rows,
        "client_peak_memory_bytes": peak_mem,
        "notes": [
            "Regex-only anonymization on CPU; BERT latency is TODO until the "
            "model is available locally.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("[cost] anon p50=%.3f ms, peak_mem=%d B"
          % (result["anonymization_latency_ms"]["p50"], peak_mem))
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
