# Ollama propio en Docker (para desplegar en Sliplane)

Contenedor de [Ollama](https://ollama.com) que, al arrancar, levanta el servidor
y descarga automáticamente el modelo configurado en la variable `OLLAMA_MODEL`.

## Requisitos

- Docker (y Docker Compose para la prueba local)
- Un repositorio de GitHub donde subir este código (Sliplane lo despliega desde ahí)

## Probar localmente

```bash
docker compose up --build
```

Una vez arranque, el servidor queda en `http://localhost:11434`.

Verificar que el modelo está cargado:

```bash
curl http://localhost:11434/api/tags
```

Probar una inferencia (endpoint compatible con OpenAI):

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma2:2b",
    "messages": [{"role": "user", "content": "Hola, ¿quién eres?"}]
  }'
```

## Modelo

Por defecto se descarga `gemma2:2b` (~1.6 GB). Nota: ni `gemma4:2b` ni
`gemma3:2b` existen en el catálogo de Ollama (Gemma 3 solo está en 1B, 4B, 12B y
27B). Alternativas: `gemma3:1b`, `gemma3:4b`, `llama3.2:3b`, etc.

Puedes cambiar el modelo con la variable de entorno `OLLAMA_MODEL`.

Para uso local, copia la plantilla y edítala (el `.env` no se sube a git):

```bash
cp .env.example .env   # y edita el modelo que quieras
```

También puedes sobrescribirlo directamente:

```bash
OLLAMA_MODEL=llama3.2:3b docker compose up
```

## Desplegar en Sliplane

1. Sube este repositorio a GitHub.
2. En Sliplane, crea un nuevo servicio y conéctalo a tu repositorio
   (ahí introduces las credenciales de acceso a GitHub que mencionas).
3. Configura el servicio:
   - **Build**: detecta automáticamente el `Dockerfile` en la raíz.
   - **Puerto**: `11434`.
   - **Volumen persistente**: monta uno en la ruta `/root/.ollama` para no
     volver a descargar el modelo en cada reinicio (1.6 GB).
   - **Variables de entorno** (opcional): `OLLAMA_MODEL=gemma2:2b`.
4. Despliega. Sliplane te dará una URL pública HTTPS, por ejemplo
   `https://tu-app.sliplane.app`.

Probar el despliegue:

```bash
curl https://TU-URL.sliplane.app/api/tags
```

## Seguridad

- Sliplane expone la app con **HTTPS** por defecto.
- **Ollama no trae autenticación**. En producción no lo dejes público sin más;
  opciones recomendadas:
  - Poner delante un proxy con autenticación (p. ej. Caddy/Nginx con Basic Auth).
  - Usar la autenticación por token que ofrezca tu plataforma si aplica.
  - Restringir el acceso por IP en el panel de Sliplane si lo permite.
- Evita exponer credenciales en el repositorio: usa las variables de entorno /
  secretos de Sliplane, nunca valores hardcodeados.

## Notas de rendimiento

Sliplane suele ofrecer solo CPU. `gemma2:2b` funciona en CPU, pero la latencia
será mayor que con GPU. Para modelos más grandes, revisa si tu plan incluye
instancias con GPU.
