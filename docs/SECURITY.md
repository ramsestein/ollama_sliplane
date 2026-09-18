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

- The message body and the credentials are protected by two independent
  AES-256-GCM layers (see `src/secure.py`).
- The Ollama server is never exposed: only the proxy listens on `0.0.0.0`.
- The proxy enforces an IP allowlist, per-IP rate limiting, anti-replay and
  trusts `X-Forwarded-For` only from configured reverse proxies.
- BERT anonymization runs on the client; the server never sees the real
  entities.

## Best practices for operators

- Always terminate TLS in front of the proxy (`REMOTE_URL` should be
  `https://...`); the application layer is encrypted, but the `/health`
  endpoint and transport metadata are not.
- Keep `ENCRYPTION_SECRET` and `AUTH_PASSWORD` out of source control and
  prefer a secrets manager (Docker secrets, managed secret stores) over
  plain environment variables when available.
- Set `TRUSTED_PROXIES`, `ALLOWED_IPS` and `RATE_LIMIT` in production.
- Pin the model with `BERT_MODEL_SHA256` to detect tampering.
