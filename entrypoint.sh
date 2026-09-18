#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-gemma2:2b}"
PROXY_PORT="${PROXY_PORT:-8000}"

# Mantener el modelo cargado en memoria para evitar arranques en frío.
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"

echo ">> Iniciando servidor Ollama..."
ollama serve &
SERVER_PID=$!

# Reenvía señales de terminación al proceso de Ollama
trap 'kill "$SERVER_PID" 2>/dev/null || true' TERM INT

echo ">> Esperando a que Ollama esté listo..."
READY=0
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:11434/api/version >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo ">> Ollama no arrancó a tiempo" >&2
  exit 1
fi

echo ">> Descargando el modelo '$MODEL' (si ya está en el volumen, lo usa directamente)..."
ATTEMPT=1
MAX_ATTEMPTS=3
until ollama pull "$MODEL"; do
  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo ">> No se pudo descargar el modelo '$MODEL' tras $MAX_ATTEMPTS intentos." >&2
    echo ">> Verifica que el nombre existe en https://ollama.com/library" >&2
    exit 1
  fi
  echo ">> Reintentando descarga ($ATTEMPT/$MAX_ATTEMPTS)..."
  ATTEMPT=$((ATTEMPT + 1))
  sleep 5
done

echo ">> Calentando el modelo '$MODEL' (carga en memoria)..."
if curl -fsS http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}],\"stream\":false}" \
    >/dev/null; then
  echo ">> Modelo cargado y residente en memoria."
else
  echo ">> Aviso: el calentamiento falló; se cargará en la primera petición." >&2
fi

echo ">> Modelo listo. Arrancando proxy cifrado en el puerto $PROXY_PORT..."
python3 /app/proxy.py &
PROXY_PID=$!

trap 'kill "$PROXY_PID" "$SERVER_PID" 2>/dev/null || true' TERM INT

wait "$PROXY_PID"
