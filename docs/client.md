# Client

Pukara ships three client entry points:

| Component | Command | Purpose |
|---|---|---|
| Desktop GUI | `python -m src.client_app` | Configuration, chat, start/stop of the local Ollama |
| CLI | `python -m src.client` | Scriptable encrypted requests |
| Local Ollama endpoint | `python -m src.local_ollama` | Ollama-compatible server for other tools |

## Desktop GUI

The window has three areas:

1. **System status** — environment checks and connection log.
2. **Configuration** (collapsible) — prefilled from `.env`; the public IP is
   auto-detected into `ALLOWED_IPS`.
3. **Chat** (collapsible) — talk to the model.

Flow:

1. Open the app: it checks the BERT model and runs minimal system checks.
2. Click **Detect IP** to refresh the auto-detected IP.
3. Click **Start**: it pings the server (`/health` → 200), starts the local
   Ollama endpoint and loads the anonymizer.
4. Type in the **Message** box and press **Send** (or Enter).
5. **Stop** (or closing the window) stops the local Ollama endpoint.

The chat pipeline is: `anonymize → encrypt → send → receive → decrypt →
deanonymize`.

## CLI

```bash
python -m src.client --url https://your-app.sliplane.app \
  --model llama3.2:3b --prompt "What is Ollama?"
```

## Local Ollama endpoint

```bash
python -m src.local_ollama
```

It listens on `http://127.0.0.1:11434` and forwards (anonymized + encrypted) to
the remote proxy, so any Ollama-compatible tool can use the remote model as if
it were local.
