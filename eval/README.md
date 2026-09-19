# Pukara evaluation harness (Phase 4)

Regenerates every figure in `docs/metrics.md` from versioned JSON files under
`eval/results/`. No number in `docs/` exists without a JSON source produced by
one of these scripts.

## Requirements

- Python 3.9+.
- `torch`, `transformers`, `numpy` for the full system (BERT + regex).
- The BERT model `BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon` under `models/`
  (already downloaded; the repo pins revision
  `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`).
- Regex-only ablation modes need only the standard library.
- Corpora must exist locally under `data/` (never pushed): `data/meddocan/corpus`
  and `data/carmen`.

## Run

```bash
make eval          # full system (BERT + regex) + utility + cost + docs/metrics.md
make eval-regex    # regex-only ablation (no model needed)
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

- **CARMEN-I**: retired as a headline metric (train overlap, no public split);
  see `docs/dev/eval-contamination.md`.
- **Round-trip**: byte-exact with the full system (0 failures in
  `eval/results/utility.json`). The regex-only ablation still emits
  overlapping/duplicate spans (e.g. a phone also matching the identifier rule)
  and would need span de-duplication in `src/anonymizer.py` if kept.
- **Word-level tokenization**: current word-level metric uses whitespace
  tokens; the official MEDDOCAN tokenizer/evaluator is pending.
- **Presidio baseline is intentionally dropped**: it is not aligned with the
  MEDDOCAN annotation guidelines and performed poorly on CARMEN-I
  (see `ramsestein/presidio_carmen`); it would not be a meaningful baseline.
- **Span-level official evaluator**: strict/relaxed implemented here; alignment
  with the official MEDDOCAN evaluator is pending.

## Conventions

- Fixed seeds and the git revision are written into every result JSON.
- `docs/metrics.md` is generated; never edit it by hand.
