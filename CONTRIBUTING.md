# Contribuir

Gracias por interesarte en este proyecto.

## Entorno de desarrollo

```bash
# 1. Clonar
git clone <url-del-repo>
cd ollama_sliplane

# 2. Crear entorno virtual e instalar dependencias de desarrollo
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt

# 3. Copiar la configuración de ejemplo
cp .env.example .env   # y edita .env con tus valores
```

> Nota: `torch` y `transformers` (en `requirements.txt`) solo son necesarios
> para la anonimización BERT. Los tests unitarios no los necesitan.

## Ejecutar los tests

```bash
python -m pytest -q
```

Los tests cubren:

- `secure.py` — cifrado/descifrado, rotación de clave y tolerancia de ventana.
- `anonymizer.py` — mapeos de etiquetas, detección por regex y placeholders reversibles.
- `proxy.py` — autenticación Basic y lista blanca de IPs.
- `local_ollama.py` — anonimización/desanonimización del cuerpo de peticiones y respuestas.

## Levantar el servidor localmente

```bash
docker compose up --build
```

## Convenciones

- Python 3.9+.
- Los secretos van en `.env` (nunca versionado) o en variables de entorno; no en el código.
- Antes de un PR, ejecuta `python -m pytest -q`.
