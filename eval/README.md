# Pukara evaluation harness (Phase 4)

Regenerates every figure in `docs/metrics.md` from versioned JSON files under
`eval/results/`. No number in `docs/` exists without a JSON source produced by
one of these scripts.

## Requirements

- Python 3.9+.
- Regex-only modes: standard library only (plus `src/`).
- BERT/combined modes: `torch`, `transformers`, `numpy`, and the gated model
  `BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon` (revision
  `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`, weights SHA-256
  `883c7c2c63d01da8af3ea12a8b22237f2896b0ce`) under `models/`.
- Corpora must exist locally under `data/` (never pushed): `data/meddocan/corpus`
  and `data/carmen`.

## Run

```bash
make eval          # regex baseline + utility + cost + docs/metrics.md
# BERT/combined (TODO until the model is downloaded):
make eval-bert     # python -m eval.meddocan --mode combined ...
```

## Scripts

| Script | Purpose |
|---|---|
| `eval/meddocan.py` | MEDDOCAN dev+test intrinsic eval: word/span P/R/F1, per-class, document leakage, bootstrap CI |
| `eval/promptbench.py` | Synthetic prompt benchmark (gold by construction): span F1, coreference consistency, collisions |
| `eval/utility.py` | Round-trip exactness and placeholder robustness under deterministic perturbations |
| `eval/cost.py` | Anonymization/encryption latency and client memory; declares hardware |
| `eval/generate_metrics.py` | Renders `docs/metrics.md` from `eval/results/*.json` |

## TODOs (explicit; no invented numbers)

- **BERT / combined modes**: require the gated model locally. Until then
  `--mode bert|combined` exits with a clear message and writes no results.
- **CARMEN-I**: retired as a headline metric (train overlap, no public split);
  see `docs/dev/eval-contamination.md`.
- **Round-trip bugs found by `eval/utility.py`**: the regex detector emits
  overlapping/duplicate spans (e.g. a phone also matching the identifier rule),
  which corrupts placeholders during replacement. Fixing this requires
  span de-duplication in `src/anonymizer.py`; until then the failures are
  reported verbatim as bugs in `eval/results/utility.json`.
- **Word-level tokenization**: current word-level metric uses whitespace
  tokens; the official MEDDOCAN tokenizer/evaluator is pending.
- **Presidio baseline** (Phase 4.2): not implemented yet; requires the Presidio
  + spaCy `es` model.
- **Span-level official evaluator**: strict/relaxed implemented here; alignment
  with the official MEDDOCAN evaluator is pending.

## Conventions

- Fixed seeds and the git revision are written into every result JSON.
- `docs/metrics.md` is generated; never edit it by hand.
