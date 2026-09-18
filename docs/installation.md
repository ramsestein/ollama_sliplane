# Installation

## Server (Docker)

1. Copy and edit the environment template:

   ```bash
   cp .env.example .env
   ```

   Set `ENCRYPTION_SECRET`, `AUTH_USER`, `AUTH_PASSWORD`, `ALLOWED_IPS` and
   `OLLAMA_MODEL`. For production also set `TRUSTED_PROXIES` (the CIDRs of
   the reverse proxy in front of Pukara), `RATE_LIMIT` and `AUDIT_LOG`.

   > The credentials are encrypted with a second key derived from
   > `OLLAMA_MODEL` + `BERT_MODEL` + `AUTH_PASSWORD`. Set `BERT_MODEL` too and
   > keep all three **identical** on the server and every client, or the
   > proxy will reject the requests with `401`. Pin the model with
   > `BERT_MODEL_SHA256` to detect tampering.

2. Build and run:

   ```bash
   docker compose up --build
   ```

   The encrypted proxy listens on port `8000`. Ollama stays internal
   (`127.0.0.1:11434`, never exposed).

## Client

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   `torch` and `transformers` (included in `requirements.txt`) are required for
   the on-device BERT anonymization.

2. Copy and edit the environment template:

   ```bash
   cp .env.example .env
   ```

   Set `REMOTE_URL` (the server URL), the same `ENCRYPTION_SECRET` as the
   server, and `AUTH_USER` / `AUTH_PASSWORD`. `OLLAMA_MODEL` and `BERT_MODEL`
   must also match the server (they are part of the credential-encryption key).

3. Download the BERT model. It is a **gated** Hugging Face repo, so first log in:

   ```bash
   huggingface-cli login
   ```

   Then either let the desktop client download it on first launch, or place it
   manually under `models/bsc-bio-ehr-es-carmen-anon/`.

4. Run the desktop client:

   ```bash
   python -m src.client_app
   # or run_client.bat (Windows) / run_client.sh (Linux)
   ```
