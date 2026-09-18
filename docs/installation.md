# Installation

## Server (Docker)

1. Copy and edit the environment template:

   ```bash
   cp .env.example .env
   ```

   Set `ENCRYPTION_SECRET`, `AUTH_USER`, `AUTH_PASSWORD`, `ALLOWED_IPS` and
   `OLLAMA_MODEL`.

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
   server, and `AUTH_USER` / `AUTH_PASSWORD`.

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
