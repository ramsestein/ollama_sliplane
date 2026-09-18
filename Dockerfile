# Imagen base oficial de Ollama
FROM ollama/ollama:latest

# curl para comprobar que el servidor está listo y para el healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Script de arranque: inicia Ollama y descarga el modelo
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Escuchar en todas las interfaces para poder exponerlo al exterior
ENV OLLAMA_HOST=0.0.0.0:11434

# Modelo que se descarga al arrancar (cambiable vía variable de entorno)
ENV OLLAMA_MODEL=gemma3:2b

EXPOSE 11434

# Volumen para persistir los modelos descargados entre despliegues
VOLUME ["/root/.ollama"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:11434/api/version >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
