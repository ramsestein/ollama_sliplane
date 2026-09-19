# PROTOCOL.md — Protocolo de evaluación de Pukara (v2)

**Estado:** congelado. Ninguna definición de métrica, partición o regla de
decisión cambia después del commit que congela este documento.
**Hash de congelado:** `__FREEZE_HASH__` (se rellena con el commit que lo
contiene, sin cambiar ninguna definición).
**Fecha:** 2026-09-19.

Este protocolo regula la segunda pasada de evaluación. Todo ajuste del detector
se hace mirando **solo** `train` y `dev`; `test` es intocable hasta la Fase G.

---

## 1. Particiones

| Partición | Documentos | Uso | Reportable |
|---|---|---|---|
| `train` | 500 | Origen de las regex (primera pasada). **Quemado.** | **No** |
| `dev` | 250 | Desarrollo, diagnóstico y ablaciones. | No (solo para mostrar cómo se eligió la configuración) |
| `test` | 250 | **Única partición reportada.** Una sola ejecución final. | **Sí** |

Notas de historia:

- `test` se ejecutó **en la primera pasada** para detectar bugs del arnés (las
  regex no se procesaban; las reglas EMAIL/URL no se ejecutaban). Desde este
  protocolo, `test` **no vuelve a ejecutarse** hasta la Fase G.
- Si por error se ejecuta `test` antes de la Fase G, se declara en el handoff;
  no se oculta.

## 2. Fusión de clases de persona en `NAME`

Se evalúa como una sola clase `NAME` la unión de:

- `NOMBRE_PERSONAL_SANITARIO`
- `NOMBRE_SUJETO_ASISTENCIA`
- `DOCTOR` (etiqueta de la regex "Dr./Dra. X")

**Justificación (antes de medir):** para seudonimizar, cualquier nombre de
persona recibe exactamente el mismo tratamiento (se sustituye por un placeholder
de tipo persona). Distinguir el rol no cambia el anonimizado ni el riesgo. El
modelo CARMEN, además, no tiene clase de paciente: emite los nombres de paciente
como `NOMBRE_PERSONAL_SANITARIO`, por lo que la fusión evita penalizar una
predicción correcta por una etiqueta de rol que el anonimizador ignora.

**Nota de desglose por subclase:** para que nadie tenga que fiarse de la fusión,
la evaluación reporta, además del agregado `NAME`, el desglose por subclase
original (`NOMBRE_PERSONAL_SANITARIO`, `NOMBRE_SUJETO_ASISTENCIA`) en
`eval/results/meddocan.json` bajo `per_class_original`. La fusión no oculta
información; solo añade una vista.

## 3. Métricas (definiciones exactas)

Todas las cifras agregadas llevan **IC 95 % bootstrap por documento, 1.000
remuestreos, semilla 42** (percentiles 2.5 / 97.5 de la media muestral).

### 3.1 Palabra (PHI/no-PHI binario)

Tokenización por espacios en blanco (`\S+`). Un token es PHI si **se solapa**
(overlap) con algún span gold; es predicho-PHI si se solapa con algún span
predicho. P/R/F1 micro sobre el total de tokens de todos los documentos.

### 3.2 Span estricto y relajado (por clase)

Sobre spans unificados (ver taxonomía en `src/anonymizer.py`):

- **Estricto:** TP si `start` y `end` coinciden exactamente entre un span gold y
  un span predicho **de la misma clase**; apareamiento 1:1 (cada span gold se
  empareja a lo sumo con un span predicho y viceversa).
- **Relajado:** TP si un span gold **se solapa** (overlap) con un span predicho
  **de la misma clase**, apareamiento 1:1. No exige coincidencia exacta de
  bordes.
- **Binario (sin clase):** además, el span estricto/relajado binario (PHI sin
  etiqueta) se reporta como `span_strict` / `span_relaxed` globales.

**Evaluador oficial de MEDDOCAN:** el script oficial
(`data/meddocan/scripts/CODALAB-Evaluation-script/`) evalúa sobre el *tagset
original* de MEDDOCAN y su subtask-2 "merged" usa una regla de fusión por
adyacencia no alfanumérica. Como Pukara evalúa la taxonomía unificada, la
implementación propia es la autoritativa para este protocolo. Para garantizar
que no nos inventamos la semántica, la implementación propia se **valida contra
el oficial en un subconjunto** (script `eval/official_check.py`, Fase C):
se re-mapean las etiquetas unificadas al tagset original y se confirma que el
conteo de spans estrictos coincide con el subtask-2 strict del oficial.

### 3.3 Neutralización label-agnostic

% de spans gold cubiertos por **cualquier** predicción que se solape, sin exigir
que la etiqueta predicha sea correcta. Un span no cubierto es un span de PHI que
sale en claro; una etiqueta equivocada **no** filtra datos.

### 3.4 Leakage por documento (dos definiciones, ambas reportadas siempre)

Un documento **filtra** si existe al menos un span gold (de las clases que
cuentan en cada definición) que no se solapa con ninguna predicción.

- **(a) Amplia (principal):** las 7 clases de la primera versión —
  `EMAIL, FAMILY, NAME, ID, PHONE, URL, PROFESSIONAL`.
- **(b) Estricta:** identificadores directos — `EMAIL, NAME, PHONE, ID`.

Ambas se reportan siempre, en `eval/results/*.json` (`leakage.wide` y
`leakage.direct`) y en `docs/metrics.md`. La amplia es la principal. No se elige
la estricta como principal: reportar solo identificadores directos subestimaría
el riesgo para clases como `PROFESSIONAL` (p. ej. "oncóloga del Hospital X")
que también re-identifican.

### 3.5 Conceptos clínicos (Fase E)

% de menciones gold de enfermedad/fármaco que quedan **byte a byte intactas**
tras la seudonimización, por corpus (DisTEMIST, PharmaCoNER) y por tipo de
concepto. IC bootstrap, semilla fija.

### 3.6 Restauración (Fase D)

- **Round-trip exacto:** `deanonymize(anonymize(x)) == x` byte a byte. Fallo =
  bug, no métrica.
- **Robustez:** % de restauraciones correctas por tipo de perturbación.
- **Restauraciones espurias:** falsos positivos de la regex de restauración
  sobre texto que contiene corchetes/guiones bajos legítimos (p. ej. JSON,
  código).

## 4. Reglas de decisión (Fase C)

- **Cambios permitidos en Fase C** (mirando solo `train`+`dev`): regex,
  umbral BERT, lista blanca, mapeo de etiquetas (no de métricas). **Prohibido**
  añadir nombres/entidades concretas de `dev` a ninguna lista.
- **Configuración final:** se elige maximizando **F1 relajado en `dev`**
  (binario, sin clase), con **leakage amplio en `dev`** como desempate. Si dos
  configuraciones empatan en F1, gana la de menor leakage amplio.
- La configuración elegida se congela con el tag **`eval-frozen-v1`**. Desde ese
  tag no se toca `src/anonymizer.py`, las regex ni la lista blanca.

## 5. Integridad de los resultados

- Cada JSON lleva `code_revision` = `git rev-parse HEAD` **en el momento de
  ejecutar**, además de `model.revision`, `weights_sha256`, `seed`, `generated`
  (fecha UTC) y `dirty`.
- Un test comprueba que el árbol está limpio (`git status --porcelain` vacío);
  si no lo está, marca el JSON con `"dirty": true`.
- Ninguna cifra se escribe a mano en `docs/metrics.md`: se genera con
  `make eval` desde `eval/results/*.json`.

## 6. Mapeo de Presidio (Fase F2) — escrito antes de ejecutar

Las entidades de Microsoft Presidio (spaCy `es_core_news_lg` + reconocedores por
defecto + reconocedores personalizados de `ramsestein/presidio_carmen`) se
mapean a la taxonomía unificada de la siguiente forma (implementado en
`eval/common.py`, confirmado contra el repo clonado antes de ejecutar):

| Entidad Presidio | Unificado |
|---|---|
| `PERSON` | `NAME` |
| `LOC`, `GPE` | `LOCATION` |
| `ORG` | `ORGANIZATION` |
| `DATE_TIME` | `DATE` |
| `PHONE_NUMBER` | `PHONE` |
| `EMAIL_ADDRESS` | `EMAIL` |
| `URL` | `URL` |
| `IBAN_CODE`, `CREDIT_CARD`, identificadores numéricos | `ID` |
| reconocedores personalizados de `presidio_carmen` | según su tipo (se documenta) |

Neutralización y leakage de Presidio se calculan **sin depender de la etiqueta**,
con el mismo evaluador que Pukara.
