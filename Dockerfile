# Imagen base de Ollama. Fija la versión para reproducibilidad
# (sobrescríbela con: --build-arg OLLAMA_BASE=ollama/ollama:otra).
ARG OLLAMA_BASE=ollama/ollama:0.34.2
FROM ${OLLAMA_BASE}

# curl (healthchecks) + python3 para el proxy cifrado.
# Se instala como root en la fase de build; después se baja a un usuario sin privilegios.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl python3 python3-cryptography \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Criptografía compartida y proxy cifrado
COPY secure.py proxy.py /app/

# Script de arranque: Ollama + descarga del modelo + proxy
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Ollama solo escucha dentro del contenedor; el proxy es la cara pública
ENV OLLAMA_HOST=127.0.0.1:11434
ENV OLLAMA_URL=http://127.0.0.1:11434
ENV PROXY_PORT=8000

# Modelo y secreto de cifrado (se sobrescriben por variables de entorno;
# el secreto NUNCA se hornea en la imagen).
ENV OLLAMA_MODEL=gemma2:2b
ENV ENCRYPTION_SECRET=""

# ── Hardening: usuario sin privilegios ─────────────────────────────────────
RUN (id app >/dev/null 2>&1 || useradd -m -u 10001 app) \
    && mkdir -p /home/app/.ollama \
    && chown -R app:app /home/app /app
ENV HOME=/home/app
ENV OLLAMA_MODELS=/home/app/.ollama
USER app

EXPOSE 8000

# Volumen para persistir los modelos descargados entre despliegues
VOLUME ["/home/app/.ollama"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
