#!/bin/sh
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[ERROR] Python not found. Install Python 3.9+."
    exit 1
fi

exec "$PY" -m src.client_app
