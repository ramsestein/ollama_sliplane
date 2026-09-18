# Contributing

Thanks for your interest in Pukara.

## Development environment

```bash
# 1. Clone
git clone <repo-url>
cd pukara

# 2. Create a virtual environment and install dev dependencies
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt

# 3. Copy the example configuration
cp .env.example .env   # edit with your values
```

> Note: `torch` and `transformers` (in `requirements.txt`) are only needed for
> BERT anonymization. The unit tests do not require them.

## Running the tests

```bash
python -m pytest -q
```

Tests cover:

- `secure.py` — encryption/decryption, key rotation and window tolerance.
- `anonymizer.py` — label mapping, regex detection and reversible placeholders.
- `proxy.py` — encrypted credentials (double encryption) and IP allowlist.
- `local_ollama.py` — request/response anonymization.

## Running the server locally

```bash
docker compose up --build
```

## Conventions

- Python 3.9+.
- Secrets go in `.env` (never committed) or environment variables, not in code.
- Run `python -m pytest -q` before opening a pull request.
