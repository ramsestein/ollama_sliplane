# Imagen base oficial de Ollama
FROM ollama/ollama:latest

# curl (healthchecks) + python3 para el proxy cifrado
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

# Modelo y secreto de cifrado (se sobrescriben por variables de entorno)
ENV OLLAMA_MODEL=gemma2:2b
ENV ENCRYPTION_SECRET=""

EXPOSE 8000

# Volumen para persistir los modelos descargados entre despliegues
VOLUME ["/root/.ollama"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
