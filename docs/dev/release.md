# Procedimiento de release — v0.2.0 (preparado, NO ejecutado)

Este procedimiento está documentado pero **no se ejecuta** en esta pasada. Solo
debe ejecutarse cuando las fases de evaluación estén completas y `docs/dev/handoff.md`
no deje preguntas abiertas.

## 0. Estado previo requerido

- `make eval` regenera `docs/metrics.md` desde `eval/results/*.json`; **ninguna
  cifra del README proviene de otra fuente**.
- El árbol está limpio (`git status --porcelain` vacío) y todos los JSON de
  `eval/results/` llevan `code_revision` igual al commit que los generó y
  `"dirty": false`.
- El detector está congelado en el tag `eval-frozen-v1` (o posterior) y
  `MEDDOCAN/test` se ejecutó exactamente una vez (ver `docs/dev/handoff.md`).

## 1. Checks previos al release

```bash
python -m pytest -q \
  --cov=src.secure --cov=src.proxy --cov-fail-under=85 --cov-report=term-missing
ruff check src tests eval
pip-audit -r requirements.txt
```

## 2. Tag y release

```bash
git checkout main
git tag -a v0.2.0 -m "Pukara v0.2.0"
git push origin v0.2.0
```

`pyproject.toml` lee la versión de `src.__version__` (fuente única), actualmente
`0.2.0`.

## 3. Zenodo

- El repositorio debe estar vinculado a un registro Zenodo (integración
  GitHub ↔ Zenodo).
- `CITATION.cff` y `.zenodo.json` llevan marcadores `TODO` para ORCIDs y el DOI
  de SoftwareX; rellenarlos antes de archivar.
- Crear un borrador de nueva versión en Zenodo para el tag `v0.2.0`, verificar
  metadatos (autores, licencia MIT, versión 0.2.0) y publicar. El DOI se añade
  a la tabla de metadatos del README (hoy "Pending").

## 4. Envío a SoftwareX

- El DOI del paso 3 va a los metadatos del manuscrito SoftwareX.
- `docs/dev/handoff.md` enumera qué afirmaciones del manuscrito quedan
  respaldadas por qué `eval/results/*.json` (sección "Segunda pasada").
