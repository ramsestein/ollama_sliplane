#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-gemma2:2b}"
PROXY_PORT="${PROXY_PORT:-8000}"

# Keep the model loaded in memory to avoid cold starts.
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

echo ">> Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Forward termination signals to the Ollama process
trap 'kill "$SERVER_PID" 2>/dev/null || true' TERM INT

echo ">> Waiting for Ollama to be ready..."
READY=0
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:11434/api/version >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo ">> Ollama did not start in time" >&2
  exit 1
fi

echo ">> Downloading model '$MODEL' (uses the volume if already present)..."
ATTEMPT=1
MAX_ATTEMPTS=3
until ollama pull "$MODEL"; do
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo ">> Could not download model '$MODEL' after $MAX_ATTEMPTS attempts." >&2
    echo ">> Check that the name exists at https://ollama.com/library" >&2
    exit 1
  fi
  echo ">> Retrying download ($ATTEMPT/$MAX_ATTEMPTS)..."
  ATTEMPT=$((ATTEMPT + 1))
  sleep 5
done

echo ">> Warming up model '$MODEL' (loading into memory)..."
if curl -fsS http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}],\"stream\":false}" \
    >/dev/null; then
  echo ">> Model loaded and resident in memory."
else
  echo ">> Warning: warm-up failed; it will load on the first request." >&2
fi

echo ">> Model ready. Starting encrypted proxy on port $PROXY_PORT..."
python3 -m src.proxy &
PROXY_PID=$!

trap 'kill "$PROXY_PID" "$SERVER_PID" 2>/dev/null || true' TERM INT

wait "$PROXY_PID"
