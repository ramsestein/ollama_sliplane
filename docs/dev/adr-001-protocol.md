# ADR-001 — Protocol v2: pre-shared key with direction-separated AES-GCM

- **Status:** accepted
- **Date:** 2026-09-19
- **Supersedes:** protocol v1 (time-window rotating keys + "auth layer")

## Context

Protocol v1 had the following verified defects (see `docs/dev/audit.md`):

1. No server-clock freshness check: an envelope declared its own time window,
   and `decrypt` accepted `window-1`, `window`, `window+1` without comparing to
   the server clock. With a 15-minute replay cache, every captured message was
   replayable after expiry.
2. The "auth layer" derived its key from
   `SHA-256(model | bert_model | password)`. Model names are public, there was
   no slow KDF, and the GCM tag acted as a verifier: an offline dictionary
   attack on the password. The auth envelope was also not bound to the message
   (no AAD) and was reusable.
3. All rotating window keys derived from the same static secret: no forward
   secrecy, no real freshness.
4. The same key was used in both directions with no domain separation and no
   request/response binding: reflection was possible.

## Decision

Replace v1 with a pre-shared-key (PSK) protocol, **v2**, built only on
`cryptography` primitives (AES-256-GCM, HKDF-SHA256):

- **Master secret** `ENCRYPTION_SECRET`: 32 random bytes, base64. Both client
  and server reject values that do not decode to ≥ 32 bytes. Generated with
  `python -m src.keygen`.
- **Derivation:** HKDF-SHA256 (salt=None) with versioned `info` strings,
  one key per direction:

      c2s = HKDF-SHA256(ikm=secret, info=b"pukara/v2/c2s")
      s2c = HKDF-SHA256(ikm=secret, info=b"pukara/v2/s2c")

  No slow KDF is needed: the secret is a random key, not a human password.
- **Envelope:** `{"v": 2, "ts": <epoch seconds>, "req_id": <16 bytes b64>,
  "nonce": <12 bytes b64>, "ciphertext": <b64>}`. `req_id` and `nonce` are
  fresh random bytes per message.
- **AAD:** fixed-length canonical encoding, never string concatenation:

      b"\x02" + direction_byte + ts.to_bytes(8, "big") + req_id

  with `direction_byte = b"\x01"` (c2s) or `b"\x02"` (s2c). Any alteration of
  `v`, `ts` or `req_id` invalidates the GCM tag.
- **Freshness:** the server rejects `|now − ts| > MAX_SKEW` (default 120 s,
  configurable), compared against its own clock, **after** tag verification.
- **Anti-replay:** a bounded cache of `req_id` with TTL ≥ 2·MAX_SKEW (always
  larger than the acceptance window) and a fail-closed policy when full. The
  check runs after tag verification.
- **Response:** encrypted with the `s2c` key; AAD carries the request's
  `req_id`. The client verifies the `req_id` matches and applies the same
  freshness check.
- **Credentials:** the auth layer is removed entirely. The client's deployment
  configuration — `user`, `password`, `model` and `bert_model` — travels inside
  the encrypted payload and is compared with `hmac.compare_digest`. Possession
  of the PSK already authenticates; this gate only enforces that the whole
  deployment configuration matches (the values are never used as key material,
  so there is no offline dictionary oracle).
- **Errors:** one generic response for tag/freshness/replay/credential failures;
  the real cause goes only to the audit log (no oracle).

## Why not HPKE / Noise-NK

| Property | PSK-v2 (this ADR) | HPKE / Noise-NK (static server key) |
|---|---|---|
| Forward secrecy | No | Yes (ephemeral DH) |
| Key distribution | One shared secret out-of-band | Server public key published; client key needed for auth variants |
| Replay/freshness | Built in (`ts` + `req_id`) | Still needs the same explicit logic |
| Dependencies | `cryptography` only | HPKE/Noise library (new dependency, more code to audit) |
| Failure modes | PSK theft decrypts recorded traffic | Private-key theft + passive recording decrypts traffic |

PSK-v2 is simpler, needs no new dependencies, and removes the four v1 defects.
Its honest limitation — **no forward secrecy; whoever steals the PSK can decrypt
recorded traffic** — is documented, not hidden. HPKE/Noise-NK with a static
server key is the stated future work.

## Consequences

- v2 breaks v1 with no backward-compatible fallback (a fallback would be a
  downgrade vector). Version bump to `0.2.0`, recorded in the CHANGELOG.
- `ENCRYPTION_SECRET` changes format (base64 of ≥ 32 bytes); old secrets are
  rejected at startup.
- Clients and servers must be deployed together.
