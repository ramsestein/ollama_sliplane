# Pukara — Phase 0 audit and hardening plan

**Status:** READ-ONLY audit. No code has been changed in this phase.
**Audited commit:** `7ecaff2` (`Doble cifrado y hardening de seguridad del proxy`), branch `main`.
**Audited:** 2026-09-18.
**Auditor scope:** `src/`, `tests/`, `docs/`, `Dockerfile`, `entrypoint.sh`,
`docker-compose.yml`, `.github/workflows/*`, `.env.example`, `.gitignore`,
`.dockerignore`, `.gitattributes`, `lista_blanca.txt`, `requirements*.txt`,
`pytest.ini`, `conftest.py`, `CITATION.cff`, `README.md`, `CONTRIBUTING.md`,
`run_client.*`, and the local model card under `models/`.

The purpose of this document is to (1) confirm the defects listed in the brief
with exact locations, (2) record **additional** findings discovered during the
audit, (3) lay out the per-phase change plan, and (4) list the decisions that
need a human answer before the work starts.

---

## 1. Confirmed defects from the brief

Each entry maps to a regression test required in Phase 1–2.

### C1. No server-clock freshness check — replay window is unbounded in practice

- **Location:** `src/secure.py:67-76` (`decrypt`), `src/proxy.py:137-153` (`_is_replay`).
- **Detail:** `decrypt()` tries windows `w, w-1, w+1` taken from the
  **envelope-declared** window and never compares against the server clock.
  An envelope built with the window of 30 days ago still decrypts (the key is
  recomputed from the declared window). The only replay protection is
  `_is_replay`, whose TTL is `3 * WINDOW_SECONDS = 900 s` (`src/proxy.py:137`),
  i.e. 15 minutes. Any captured request is replayable forever after 15 minutes.
- **PoC (minimal):**
  ```python
  from src import secure
  e = secure.encrypt(secret, b"x", window=secure.current_window() - 17280)  # 30 days ago
  secure.decrypt(secret, e)  # succeeds
  ```
- **Regression test:** timestamp older than `MAX_SKEW` rejected; timestamp in the
  future rejected; both compared against the server's own clock.

### C2. Auth layer is an offline dictionary oracle, not a second factor

- **Location:** `src/secure.py:85-97` (`_auth_key_base`, `_derive_auth_key`).
- **Detail:** `base = SHA-256(model | bert_model | password)`. `model` and
  `bert_model` are public identifiers; there is no slow KDF; the AES-GCM tag of
  the auth envelope acts as a verifier. An attacker with one captured envelope
  can mount an offline dictionary attack on the password. Additionally the auth
  envelope has **no AAD** binding it to the message, so it is reusable across
  requests. It is also **not** double encryption: it is a second, parallel
  envelope (`src/proxy.py:222`, `src/client.py:39-42`).
- **PoC:** brute-force `password` against a captured `auth` envelope using
  public `model`/`bert_model` and the GCM tag as the check.
- **Regression test:** absence of the auth layer entirely (Phase 1 removes it);
  no `encrypt_auth`/`decrypt_auth`/`build_auth_envelope` symbols remain.

### C3. Rotating keys derive from one static secret — no forward secrecy, no freshness

- **Location:** `src/secure.py:41-45` (`_derive_key`).
- **Detail:** every window key is `HMAC(secret, "ollama-secure:{window}")`.
  Compromising `ENCRYPTION_SECRET` reveals all past and future traffic.
- **Regression test:** KAT vectors for derivation (Phase 1), and documentation
  of the PSK limitation (no forward secrecy).

### C4. No direction separation → reflection

- **Location:** `src/secure.py:27-45` (single `_DERIVE_CTX`), reused for both
  request encryption (`src/client.py`, `src/local_ollama.py`) and response
  encryption (`src/proxy.py:273`).
- **Detail:** the same key encrypts both directions with the same context and no
  request/response binding. A request envelope can be replayed as a response
  envelope and vice versa.
- **PoC:** capture a client `{window,nonce,ciphertext}` request and replay it as
  the server's response body; `secure.decrypt` accepts it.
- **Regression test:** reflection of a request presented as a response is
  rejected (Phase 1, `s2c` key + `req_id` AAD).

### C5. SSRF via upstream URL concatenation; no route/method allowlist

- **Location:** `src/proxy.py:253` (`OLLAMA_URL + path`).
- **Detail:** `path` comes from the decrypted inner request and is concatenated
  raw. `path="@example.com/x"` turns `http://127.0.0.1:11434@example.com/x`,
  which `urllib` resolves to `example.com`. There is no `(method, path)`
  allowlist, so `/api/pull`, `/api/delete`, `/api/create`, `/api/copy`,
  `/api/push` are all reachable through the proxy.
- **PoC:** `POST /secure/request` with inner `{"method":"GET","path":"@attacker.example/x"}`.
- **Regression test:** URL is built with `urllib.parse` and validated against
  `OLLAMA_URL`; paths with `@`, `\`, `//`, control characters, or not starting
  with `/` are rejected; non-allowlisted routes/methods are denied.

### C6. Unbounded `Content-Length` and unbounded in-memory structures

- **Location:** `src/proxy.py:214` (`length = int(...)` + `rfile.read(length)`),
  `src/proxy.py:120-132` (`_rate_hits`), `src/proxy.py:139-153` (`_seen`).
- **Detail:** no body-size cap before reading; `_rate_hits` grows one list per
  distinct IP (pruned only when that IP returns); `_seen` is pruned by a full
  O(n) scan on every request and can grow without bound if the replay TTL is
  never reached for the stored keys.
- **Regression test:** oversized body rejected before read (413); caches are
  bounded with a fail-closed policy when full.

### C7. `/health` leaks internal state

- **Location:** `src/proxy.py:190-191`.
- **Detail:** returns `{"ok": true, "window": ...}` — the time-window counter is
  internal state that helps an attacker time replays.
- **Regression test:** `/health` returns exactly `{"ok": true}`.

### C8. Default model repo is likely wrong and unpinned

- **Location:** `src/anonymizer.py:22`, `src/client_app.py:28`, `.env.example:9`,
  `docker-compose.yml:13`.
- **Detail:** the default is `PlanTL-GOB-ES/bsc-bio-ehr-es-carmen-anon`, but the
  model card in `models/bsc-bio-ehr-es-carmen-anon/README.md` declares
  `model-index: name: BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon`, and
  `config.json` has `_name_or_path: PlanTL-GOB-ES/bsc-bio-ehr-es` (the **base**
  RoBERTa, not the fine-tuned repo). No `revision` (commit hash) is pinned, and
  `BERT_MODEL_SHA256` defaults to empty (`verify_model_hash` returns `True` when
  unset — fail-open, `src/anonymizer.py:48-65`).
- **Action:** determine which repo resolves and correct it; pin `revision` and
  the weights SHA-256. Decision needed in §4.

---

## 2. Additional findings (not in the brief)

### A1. Fail-open defaults for IP allowlist and credentials (High)

- **Location:** `src/proxy.py:86` (`return True  # no list configured => no
  restriction`) and `src/proxy.py:101` (`return True  # no credentials
  configured => no restriction`).
- **Detail:** with the default `docker-compose.yml` (`AUTH_USER`/`AUTH_PASSWORD`
  empty, `ALLOWED_IPS` empty), the proxy is open to any network peer that holds
  the PSK, and with no IP restriction at all. The brief requires fail-closed
  startup with a loud warning and a `STRICT=1` mode that refuses to boot.
- **Regression test:** startup warns when `ALLOWED_IPS`/credentials missing;
  `STRICT=1` exits non-zero.

### A2. Error oracle distinguishes failure causes (Medium)

- **Location:** `src/proxy.py:197-245`.
- **Detail:** distinct status codes and bodies distinguish IP (403), rate limit
  (429), auth (401 + `WWW-Authenticate`), decrypt (400) and replay (409). The
  brief requires a single generic response for tag/freshness/replay/credentials
  failures, with the real cause only in the audit log.
- **Regression test:** identical response for all four failure classes.

### A3. Audit log lacks `req_id`, reject reason and size (Medium)

- **Location:** `src/proxy.py:155-171` (`_audit`).
- **Detail:** only `ts`, `ip`, `method`, `path`, `status`. No request id, no
  rejection cause, no body size. Good: it never logs bodies.
- **Regression test:** audit lines include `req_id`, reject reason and size.

### A4. Response is not bound to the request — response substitution (High)

- **Location:** `src/proxy.py:273`, `src/client.py:44-52`.
- **Detail:** the server encrypts the response with the same key and no AAD over
  the request `req_id`; the client decrypts without checking anything about the
  request. A captured/reflected envelope can be injected as a response.
- **Regression test:** response whose AAD `req_id` does not match the request is
  rejected (Phase 1).

### A5. Upstream response read is unbounded (Medium)

- **Location:** `src/proxy.py:259` (`resp.read()`).
- **Detail:** the whole Ollama response is read into memory with no size cap and
  a 600 s timeout. Non-streaming but large responses (e.g. `/api/embed`, long
  generations) are unbounded.
- **Regression test:** response-size cap and read timeout enforced.

### A6. `verify_model_hash` is fail-open (Medium)

- **Location:** `src/anonymizer.py:48-65`.
- **Detail:** returns `True` when no hash is configured **and** when no weights
  file is found. A missing `BERT_MODEL_SHA256` silently disables integrity
  checking. Phase 5 should require the hash in CI/eval and fail closed when the
  environment expects it.

### A7. Local endpoint is CORS-open and unauthenticated → browser-driven misuse (High)

- **Location:** `src/local_ollama.py:156,173`
  (`Access-Control-Allow-Origin: *`).
- **Detail:** the local server on `127.0.0.1:11434` accepts cross-origin
  requests with no local authentication. Any website open in the user's browser
  can POST to the local endpoint (the wildcard CORS + allowed headers/methods
  pass preflight), causing prompts to be anonymized and sent to the remote model
  (cost and data egress), and responses read back. Classic localhost-service
  CSRF/DNS-rebinding exposure.
- **Mitigation candidates (Phase 2):** bind to `127.0.0.1` (already), drop or
  restrict CORS to a configurable origin, add a random per-start local token, or
  reject requests whose `Origin`/`Host` are not `localhost`/`127.0.0.1`.

### A8. Arbitrary path forwarding in the local endpoint (Medium)

- **Location:** `src/local_ollama.py:207` (`forward("GET", self.path)`) and
  `src/local_ollama.py:246-252` (POST fallback).
- **Detail:** any local process can ask the local endpoint to forward arbitrary
  upstream paths (including model-management routes) through the encrypted
  proxy. Once the proxy allowlist exists (Phase 2), this needs to be mirrored
  here or the local endpoint must reject management routes too.

### A9. Anonymizer round-trip is not guaranteed for adversarial input (Medium)

- **Location:** `src/anonymizer.py:500-503` (`deanonymize` uses `str.replace`).
- **Detail:** if the original text already contains a literal placeholder
  (`[NOMBRE_1]`, nested brackets, overlapping entities), or if a detected
  entity's text equals a generated placeholder string, `deanonymize(anonymize(x))`
  can diverge from `x`. Phase 4.4 requires this as a property test
  (`deanonymize(anonymize(x)) == x` byte-for-byte), so the placeholder design
  may need a collision-proof format.
- **PoC:** text `"El valor [NOMBRE_1] es X"` where the regex later assigns
  `[NOMBRE_1]` to a real entity → ambiguous reversal.

### A10. Whitelist also consulted in the BERT path and skips location by default (Medium)

- **Location:** `src/anonymizer.py:376-378` (BERT entities skipped if in
  `LISTA_BLANCA`) vs `src/anonymizer.py:398-408` (regex `location` has no
  whitelist check).
- **Detail:** behavior is inconsistent between detectors: a term whitelisted
  (e.g. `barcelona`, see §5) is dropped by BERT but can be re-added by the regex
  `location` rule. The whitelist therefore does not reliably mean "never
  anonymize".
- **Action:** clarify in Phase 2 whether the whitelist is an FP-suppression list
  (per-detector) or a hard allowlist, and make the two paths consistent.

### A11. `family_relation` regex over-redacts gender/kinship words (Medium, utility)

- **Location:** `src/anonymizer.py:139-140` (pattern includes `mujer`, `marido`,
  `dona`, `viejo`, `vieja`, etc.).
- **Detail:** generic words such as "mujer" ("woman") are treated as PHI
  (`FAMILY`) regardless of context. This is an over-redaction / utility issue to
  quantify in Phase 4.4 (percentage of non-PHI tokens altered).

### A12. Version/consistency drift across the repo (Low)

- **Location:** `README.md` badge `0.1.0`, `CITATION.cff` `version: 0.1.0`,
  `src/client_app.py:261` window title `"Pukara v1.0"`.
- **Detail:** three different versions in play; no single source of truth. Phase
  5 introduces `pyproject.toml` as the single source and bumps to `0.2.0`.

### A13. CI gaps (Medium)

- **Location:** `.github/workflows/ci.yml`.
- **Detail:** single Python `3.11`; installs only `cryptography pytest` (not the
  real test dependencies); `pip-audit` is `continue-on-error: true`; no `ruff`;
  no coverage gate. Phase 5 fixes all of these.

### A14. `client_app.py` does not reset the placeholder map per conversation (Low)

- **Location:** `src/client_app.py:534-536` (map persists across sends) vs
  `src/local_ollama.py:236` (resets per request).
- **Detail:** the GUI accumulates the map for the whole session and only resets
  on Stop (`src/client_app.py:476`). Cross-conversation map growth is minor, but
  the brief's "reset per conversation" should be reconciled with multi-turn
  consistency (which needs the map to persist within a conversation).

### A15. Secrets stored in plaintext `.env` on the client (Informational)

- **Location:** `src/client_app.py:54-70` (`save_env`).
- **Detail:** expected for a desktop client, but worth stating in the threat
  model as the client-side secret-at-rest boundary.

---

## 3. Phase plan (for review)

- **Phase 0 (this document):** audit + plan. ✅ Delivered; awaiting review.
- **Phase 1 — Protocol v2 (`src/secure.py`):** PSK + HKDF-SHA256 with
  `pukara/v2/c2s` / `pukara/v2/s2c`; envelope `{v, ts, req_id, nonce,
  ciphertext}`; canonical AAD (`v | direction | ts | req_id`); `MAX_SKEW`
  freshness vs server clock; bounded fail-closed `req_id` replay cache with
  TTL ≥ 2·MAX_SKEW; response bound to request `req_id`; credentials inside the
  payload compared with `hmac.compare_digest`; single generic error; remove the
  auth layer; `python -m src.keygen`; KAT vectors. `docs/dev/adr-001-protocol.md`.
  Regression tests cover C1–C4 + A2 (partial) + the "must fail on current main"
  list.
- **Phase 2 — Proxy + client:** `(method, path)` allowlist; safe URL building
  with `urllib.parse`; body cap (10 MB default); read timeouts; bounded caches;
  fail-closed startup + `STRICT=1`; minimal `/health`; audit log with `req_id`,
  reason, size; streaming documented as a limitation; client map in memory only
  with per-conversation reset (decide A14); review `lista_blanca.txt` (§5).
  Covers C5–C7, A1, A3, A5, A7, A8.
- **Phase 3 — Threat model:** `docs/threat-model.md` (assets, actors, trust
  boundaries + Mermaid DFD, assumptions, STRIDE per component, out-of-scope,
  pseudonymisation wording). Wire every mitigation to a test. Update README and
  SECURITY.md.
- **Phase 4 — Evaluation:** `eval/` with the exact structure in the brief
  (4.0 contamination audit → 4.6 generated `docs/metrics.md`). All numbers must
  come from `eval/results/*.json`.
- **Phase 5 — Packaging:** `pyproject.toml` single version `0.2.0`, entry points,
  CI matrix 3.9–3.12, `ruff`, coverage ≥ 85 % on `secure.py`/`proxy.py`,
  `pip-audit` without `continue-on-error`, integration tests against a fake
  Ollama, `CHANGELOG.md`, `.zenodo.json`, `CITATION.cff` with ORCIDs,
  `CODE_OF_CONDUCT.md`, dependabot triage, README rewrite.

---

## 4. Decisions that need a human answer

> **Resolved (2026-09-19):** model repo = `BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon`
> (revision `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`; weights SHA-256
> `883c7c2c63d01da8af3ea12a8b22237f2896b0ce`). Corpora live in `data/` (never
> pushed; added to `.gitignore`). MEDDOCAN evaluation uses `dev`+`test` (1,000
> docs; `train` was used to calibrate the tool and is excluded). CARMEN-I is
> train-contaminated and must be demoted. Affiliations/ORCID deferred. Each
> model conversation is unique, in-memory only, no persistence, map reset per
> conversation. Auth tokens (secret + user/password) must match or the proxy
> rejects. Whitelist pruning: keep only the clinical abbreviation/acronym
> sections, remove the rest.

1. **Model repo and pinning (C8).** Which Hugging Face repo is authoritative for
   `bsc-bio-ehr-es-carmen-anon` — `PlanTL-GOB-ES/...` or `BSC-NLP4BIA/...`? We
   need the commit hash (`revision`) and the SHA-256 of the weights to pin.
2. **CARMEN-I split (Phase 4.0).** The model is fine-tuned on CARMEN-I; the
   current "CARMEN test (2,000 docs)" result is likely train-overlap. Can the
   authors provide the exact train/test split? If not, we retire CARMEN as a
   headline result and label it "in-distribution, upper bound, possible train
   overlap".
3. **MEDDOCAN usage.** Were the 100 validation documents (or any others) used to
   calibrate the threshold, whitelist or regexes? Everything used for
   calibration must be excluded from the clean evaluation set.
4. **Corpus access.** CARMEN-I requires PhysioNet credentials; MEDDOCAN is a
   download. Confirm the evaluation machine has (or can obtain) the corpora, so
   `make eval` is reproducible. If not, we ship the harness with explicit TODOs
   and empty tables (no invented numbers).
5. **ORCIDs and affiliations** for `CITATION.cff` / `.zenodo.json` (currently
   `authors: ["Marrero Garcia, Ramsés", "Peñafiel, Petter Axel"]` with no
   identifiers).
6. **DOI.** Leave the SoftwareX DOI as a placeholder until the release.
7. **Streaming.** Confirm streaming stays out of scope for v0.2.0 (documented as
   a limitation), as the brief states.
8. **A14 (map reset per conversation).** Confirm the desired behavior for the
   GUI: reset per conversation vs. per session, balancing coreference
   consistency against map growth.
9. **A7 (local endpoint CORS).** Accept a local random token / restricted CORS,
   or leave the local endpoint trusted to `127.0.0.1` only (documented)?
10. **Whitelist pruning (§5).** Approve removing (or keeping) the doubtful terms
    listed below before Phase 2.

---

## 5. Doubtful `lista_blanca.txt` terms (potential anonymization bypass)

Terms that can also be surnames, toponyms or identifiers, and therefore bypass
detection when they refer to a person/place. Not deleted without approval:

| Term | Risk |
|---|---|
| `barcelona` | toponym; also present in `MEDICAL_ACRONYMS` and the `location` regex |
| `Hamilton` | surname (Hamilton Depression Rating Scale) |
| `Young` | surname (Young Mania Rating Scale) |
| `hamilton`/`young` derivatives | same as above |
| `EPS`, `PV`, `RE`, `EA`, `OD`, `FA`, `AP`, `AB`, `NP`, `TA`, `TB` | two-letter acronyms; also plausible person initials (low, patterns need 3+ uppercase) |
| `dm`, `hta`, `fa` (lowercase in some entries) | could collide with short names in `name_mixed` (low) |
| `viejo`, `vieja`, `mujer`, `marido`, `dona` | kinship/gender words; over-redaction concern rather than bypass |

Recommended: move unambiguous clinical acronyms/drugs to a curated
FP-suppression list; treat anything that can be a person/toponym/identifier as
detectable, and rely on the NER/regex for the decision. Final call in Phase 2.

---

## 6. Statements that must be removed or qualified

Confirmed occurrences of absolute or misleading wording (rule 5 of the brief):

- `README.md:35-37` — "**rotating key**", "the server only ever sees reversible
  placeholders **it cannot undo**".
- `README.md:62-74` — "double-layered / two independent AES-256-GCM layers".
- `README.md:81` — "double encryption".
- `docs/SECURITY.md:35` — "the server never sees the real entities".
- `src/anonymizer.py:8-10` — "the server never sees the real data".
- `src/secure.py:1-4` — module docstring ("double encryption", "rotating keys").
- `docs/metrics.md` — CARMEN/MedDocAn figures with no versioned JSON source;
  to be regenerated or retired in Phase 4.
- `.env.example:28-30`, `docs/installation.md:16-19`, `CONTRIBUTING.md:36-38`,
  `src/local_ollama.py:53`, `src/proxy.py:16,95`, `tests/test_secure.py:1` —
  "double encryption" wording.

These will be rewritten in Phases 1–3 and 5.

---

## 7. What this phase deliberately does NOT do

- No code changes, no dependency changes, no config changes.
- No new tests yet (they will be written in Phase 1+ and must fail on current
  `main`).
- No evaluation numbers; the eval harness is Phase 4.
