# Auditoría de contaminación de evaluación

**Fecha:** 2026-09-19. **Estado:** reescrito desde el estado actual.

Este documento fija qué corpus es válido para qué afirmación. Ningún resultado
de `docs/` puede sostenerse si no pasa esta auditoría.

## 1. CARMEN-I: retirado como métrica principal (solape de entrenamiento)

- La model card
  ([`BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon`](https://huggingface.co/BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon))
  declara que el modelo se entrenó sobre la parte de anonimización de CARMEN-I y
  **no** publica una partición train/test.
- La página del corpus (PhysioNet, 10.13026/x7ed-9r91) describe CARMEN-I como un
  recurso único de **2.000 documentos** sin partición oficial publicada.
- La cifra anterior ("CARMEN test, 2.000 documentos") evalúa sobre el corpus
  completo, que es también sobre lo que se ajustó el modelo.

**Conclusión:** la partición usada para el ajuste fino no puede determinarse. La
cifra de CARMEN-I es *in-distribution, cota superior, posible solape con
entrenamiento* y **no** se usa como resultado principal. En la Fase F2 se
ejecuta de nuevo como **tabla secundaria** (continuidad con cifras publicadas y
para mostrar el tamaño de la caída in-distribution → fuera de distribución), con
la nota de solape **dentro de la tabla**, no en pie de página.

## 2. MEDDOCAN: limpio de entrenamiento, con `train` quemado por derivación de regex

- El modelo se entrenó solo sobre CARMEN-I. MEDDOCAN (Marimon et al., IberLEF
  2019) **no** formó parte del entrenamiento del modelo.
- Datos locales `data/meddocan/corpus/`: `train` (500), `dev` (250), `test`
  (250) documentos en formato brat.
- **`train` está quemado**: de ahí se derivaron las regex en la primera pasada.
  No es reportable.
- **`dev`** = desarrollo y ablaciones. **`test`** = única partición reportada,
  una sola ejecución final.

## 3. DisTEMIST y PharmaCoNER (Fase E): fuera de entrenamiento

Verificado en la Fase E antes de medir: ninguno de los dos corpus forma parte
del entrenamiento del modelo CARMEN (que se entrenó solo con la parte de
anonimización de CARMEN-I). Se citan sus fuentes primarias en
`eval/concepts.py`.

## 4. Reglas operativas

1. CARMEN-I nunca es resultado principal; si aparece, va etiquetado
   "in-distribution, cota superior, posible solape con entrenamiento".
2. `train` de MEDDOCAN no se reporta jamás.
3. `test` de MEDDOCAN se ejecuta **una sola vez**, al final, con el código
   congelado por commit (`eval-frozen-v1`).
4. Toda cifra de `docs/` proviene de `eval/results/*.json` generado por
   `make eval`; no se editan cifras a mano.
