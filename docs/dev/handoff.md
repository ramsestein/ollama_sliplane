# Handoff — Pukara hardening for SoftwareX

Date: 2026-09-19. Branches (one per phase, all with green tests):

| Phase | Branch | Head |
|---|---|---|
| 0 | `main` | `53c3aea` |
| 1 | `fase1-protocolo-v2` | `606ccec` |
| 2 | `fase2-proxy` | `84ccf5e` |
| 3 | `fase3-threat-model` | `e10da36` |
| 4 | `fase4-evaluacion` | `f9553d3` |
| 5 | `fase5-empaquetado` | (this branch) |

## What was done

- **Protocol v2** (`src/secure.py`): PSK + HKDF-SHA256, direction-separated
  keys, canonical AAD, server-clock freshness, bounded fail-closed anti-replay,
  response/request binding, credentials+config inside the payload compared with
  `hmac.compare_digest`. `src/keygen.py`. ADR in `docs/dev/adr-001-protocol.md`.
- **Proxy hardening** (`src/proxy.py`): `(method, path)` allowlist, safe URL
  building with `urllib.parse`, 10 MB body limit, bounded rate/replay
  structures, fail-closed startup with `STRICT=1`, minimal `/health`, audit log
  with `req_id`/reason/size, generic denial (no oracle). Local endpoint: CORS
  restricted to local origins, management routes denied.
- **Whitelist**: kept as the clinical no-anonymise list (diseases, drugs,
  procedures, abbreviations); only the bypass terms `barcelona`, `Hamilton`,
  `Young` were removed (and `barcelona` from `MEDICAL_ACRONYMS`).
- **Threat model** (`docs/threat-model.md`) cited from README and SECURITY.md.
- **Evaluation harness** (`eval/`): MEDDOCAN intrinsic eval, synthetic
  promptbench, utility (round-trip + placeholder robustness), cost,
  `docs/metrics.md` generator, `Makefile`. `make eval` regenerates the numbers.
- **Packaging**: `pyproject.toml` (version from `src.__version__`), entry points
  `pukara-keygen`/`pukara-proxy`/`pukara-client`, CI matrix 3.9–3.12 with
  `ruff`, ≥85% coverage on `secure.py`/`proxy.py`, and `pip-audit` without
  `continue-on-error`. Integration tests proxy↔client with a fake Ollama.
  `CHANGELOG.md`, `.zenodo.json`, `CODE_OF_CONDUCT.md`, `CITATION.cff` updated.

## What remains pending

- **BERT / combined evaluation**: requires downloading the gated model
  `BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon` (revision
  `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`, SHA-256
  `883c7c2c63d01da8af3ea12a8b22237f2896b0ce`) under `models/`. Until then
  `--mode bert|combined` exits without writing numbers (rule 1: no invented
  figures).
- **Round-trip**: byte-exact with the full system (0 failures in
  `eval/results/utility.json`). The regex-only ablation has the overlapping-span
  bug (span de-duplication would be needed only for that ablation).
- **Presidio baseline**: intentionally dropped — not aligned with MEDDOCAN
  guidelines and performed poorly on CARMEN-I (`ramsestein/presidio_carmen`).
- **Official MEDDOCAN tokenizer/evaluator**: word-level uses whitespace tokens;
  strict/relaxed span eval is implemented.
- **Dependabot PR triage**: not performed here (no repository PR access from
  this environment). Merge the safe updates, comment the rest.
- **Release procedure**: documented in `docs/dev/release.md`, not executed.

## Decisions that still need the authors

1. **CARMEN-I split**: which partition was used to fine-tune
   `bsc-bio-ehr-es-carmen-anon`? Until answered, CARMEN-I stays demoted to
   "in-distribution, upper bound, possible train overlap"
   (`docs/dev/eval-contamination.md`).
2. **Corpus access**: CARMEN-I needs PhysioNet credentials; confirm the eval
   machine has them (the files are local under `data/`, never pushed).
3. **ORCIDs and affiliations** for `CITATION.cff` / `.zenodo.json` (TODO
   markers in place).
4. **DOI**: SoftwareX DOI to fill after the Zenodo release.

## Manuscript claims and their backing results

| Claim (future manuscript) | Backed by |
|---|---|
| v2 prevents timestamp rollback | `tests/test_secure.py::test_old_timestamp_rejected`, `test_future_timestamp_rejected` |
| v2 prevents replay | `test_replay_within_ttl_rejected`, `test_replay_rejected_at_window_edge` |
| v2 prevents reflection | `test_reflection_request_as_response_rejected`, `test_response_with_foreign_req_id_rejected` |
| v2 rejects header tampering | `test_header_tampering_fails` |
| Config must fully match | `tests/test_proxy.py::test_config_*`, `tests/test_integration.py::test_wrong_config_denied` |
| SSRF prevented | `tests/test_proxy.py::test_upstream_url_rejects_host_trick`, `test_validate_path` |
| Management routes denied | `tests/test_proxy.py::test_route_allowed_management_denied`, `tests/test_integration.py::test_management_route_denied` |
| MEDDOCAN regex baseline (word F1, leakage, per-class) | `eval/results/meddocan.json` |
| PHI neutralization (label-agnostic coverage) | `eval/results/meddocan.json` (`phi_neutralization`) |
| Synthetic prompt performance / coreference consistency | `eval/results/promptbench.json` (5,000 prompts) |
| Round-trip and placeholder robustness | `eval/results/utility.json` |
| Latency and memory | `eval/results/cost.json` |
