# Ollama base image. Pin the version for reproducibility
# (override at build time: --build-arg OLLAMA_BASE=ollama/ollama:other).
ARG OLLAMA_BASE=ollama/ollama:0.34.2
FROM ${OLLAMA_BASE}

# curl (health checks) + python3 for the encrypted proxy.
# Installed as root during build; we drop to an unprivileged user afterwards.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl python3 python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Shared cryptography and encrypted proxy
COPY src/ /app/src/

# Bootstrap script: Ollama + model download + proxy
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Ollama listens only inside the container; the proxy is the public face
ENV OLLAMA_HOST=127.0.0.1:11434
ENV OLLAMA_URL=http://127.0.0.1:11434
ENV PROXY_PORT=8000

# Model and encryption secret (overridden via environment variables;
# the secret is NEVER baked into the image).
ENV OLLAMA_MODEL=gemma2:2b
ENV ENCRYPTION_SECRET=""

# ── Hardening: unprivileged user ───────────────────────────────────────────
RUN (id app >/dev/null 2>&1 || useradd -m -u 10001 app) \
    && mkdir -p /home/app/.ollama \
    && chown -R app:app /home/app /app
ENV HOME=/home/app
ENV OLLAMA_MODELS=/home/app/.ollama
USER app

EXPOSE 8000

# Volume to persist downloaded models across deployments
VOLUME ["/home/app/.ollama"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
