# Security Policy

## Supported versions

Only the latest release on the `main` branch is supported with security
fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report them privately to the maintainers so they can be fixed
before disclosure. A typical report includes:

- A short description of the vulnerability.
- Steps to reproduce it (minimal example).
- The affected component (`src/secure.py`, `src/proxy.py`, the Docker
  image, etc.).
- Impact and, if possible, a suggested fix.

We will acknowledge your report as soon as possible and aim to publish a
fix and a coordinated advisory.

## Security model

The authoritative description is
[`docs/threat-model.md`](threat-model.md).

- Client ↔ proxy traffic is protected by protocol v2: direction-separated
  AES-256-GCM with HKDF-SHA256 key derivation, server-clock freshness, and a
  bounded anti-replay cache (see `src/secure.py` and
  `docs/dev/adr-001-protocol.md`).
- The Ollama server is only reachable inside the container; only the proxy
  listens on `0.0.0.0`.
- The proxy enforces an explicit `(method, path)` allowlist, an IP allowlist,
  per-IP rate limiting, anti-replay, a request-body limit, and trusts
  `X-Forwarded-For` only from configured reverse proxies.
- BERT pseudonymisation runs on the client; the placeholder map never leaves
  the client. Whether the transmitted text is anonymous for the recipient
  depends on the residual re-identification risk (see the threat model and
  `docs/metrics.md`).

## Best practices for operators

- Always terminate TLS in front of the proxy (`REMOTE_URL` should be
  `https://...`); the application layer is encrypted, but the `/health`
  endpoint and transport metadata are not.
- Keep `ENCRYPTION_SECRET` and `AUTH_PASSWORD` out of source control and
  prefer a secrets manager (Docker secrets, managed secret stores) over
  plain environment variables when available.
- Set `TRUSTED_PROXIES`, `ALLOWED_IPS` and `RATE_LIMIT` in production.
- Pin the model with `BERT_MODEL_SHA256` to detect tampering.
