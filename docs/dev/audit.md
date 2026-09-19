# Pukara — Auditoría consolidada (segunda pasada)

**Estado:** reescrito desde el estado actual del repositorio. No se restaura la
versión borrada; se reconstruye con `git show 8754c1b:docs/dev/audit.md` solo
como referencia.
**Fecha:** 2026-09-19.
**Commit auditado:** `cd095c7` (`Separar stack ML del cliente y auditar solo el
núcleo con pip-audit`), rama `main`.
**Alcance:** `src/`, `eval/`, `docs/`, `tests/`, `lista_blanca.txt`,
`requirements*.txt`, `Makefile`.

La auditoría original (fase 0, sobre `7ecaff2`) está integrada aquí como
§1. Esta segunda pasada añade los hallazgos surgidos al leer el historial de
resultados commit a commit y al revisar el detector y el arnés con disciplina
de evaluación (§2).

---

## 1. Hallazgos originales: estado

| ID | Hallazgo | Estado |
|---|---|---|
| A1 | Fail-open de allowlist IP y credenciales | **Resuelto** `84ccf5e` (fase 2): arranque fail-closed + `STRICT=1`. |
| A2 | Oráculo de errores distingue causas de fallo | **Resuelto** `606ccec` (fase 1): respuesta genérica única. |
| A3 | Log de auditoría sin `req_id`, razón ni tamaño | **Resuelto** `84ccf5e`. |
| A4 | Respuesta no ligada a la petición (sustitución) | **Resuelto** `606ccec`: AAD liga la respuesta al `req_id`. |
| A5 | Lectura de respuesta upstream sin acotar | **Resuelto** `84ccf5e`: límite de cuerpo y timeouts. |
| A6 | `verify_model_hash` fail-open | **Parcial.** El hash y la revisión están fijados en `eval/common.py` (`MODEL_META`); el cargador de `src/anonymizer.py` sigue devolviendo `True` si `BERT_MODEL_SHA256` no está definido. Documentado como riesgo residual en `docs/SECURITY.md`. |
| A7 | Endpoint local con CORS abierto y sin autenticar | **Resuelto** `84ccf5e`: CORS restringido a orígenes locales. |
| A8 | Forwarding de rutas arbitrarias en el endpoint local | **Resuelto** `84ccf5e`: rutas de gestión denegadas. |
| A9 | Round-trip no garantizado para input adversarial | **Resuelto en esta pasada (Fase D):** `deanonymize` reescrito con restauración por regex tolerante y test de propiedad. |
| A10 | Whitelist inconsistente entre BERT y regex | **Resuelto** `84ccf5e` (poda de términos dudosos); re-auditado en la Fase C de esta pasada. |
| A11 | `family_relation` sobre-redacta palabras genéricas | **Mitigado en esta pasada (Fase C):** sobre-redacción medida y reducida. |
| A12 | Deriva de versiones (README `0.1.0` vs `v1.0`) | **Resuelto** `86e1663`: versión única `0.2.0` desde `src.__version__`. |
| A13 | Gaps de CI | **Resuelto** `86e1663` + `cd095c7`: matriz 3.9–3.12, `ruff`, cobertura ≥85 %, `pip-audit` sin `continue-on-error`. |
| A14 | El mapa de placeholders no se reinicia por conversación | **Resuelto** (fase 5): mapa en memoria con reinicio por conversación. |
| A15 | Secretos en `.env` plano en el cliente | **Documentado** en `docs/threat-model.md` (límite secret-at-rest del cliente). |
| C1–C8 | Decisiones de modelo, corpus y configuración | **Resueltas** (bloque "Resolved" de la auditoría original): repo `BSC-NLP4BIA/bsc-bio-ehr-es-carmen-anon`, revisión `83db1112c37c7ef527a9ba6d6b4d1be18b4bca9b`; corpora en `data/` (nunca subidos); CARMEN-I degradado por solape de entrenamiento. |

---

## 2. Hallazgos nuevos de esta pasada

### N1. El historial de leakage contiene lecturas espurias (lectura commit a commit)

El historial de `eval/results/meddocan.json` (leakage 100 % → 70 % → 18,2 % →
28,4 %) no es una secuencia de ajustes. Leído commit a commit:

- `f9553d3` → `30fb7e2`: la primera ejecución **no procesaba las regex** (bug
  del arnés); se corrigió. **No es un ajuste del detector.**
- `8754c1b`: las reglas EMAIL/URL **no se ejecutaban** (bug preexistente,
  detectado sin mirar `dev` ni `test`); se corrigió. **No es un ajuste.** En el
  mismo commit se **estrechó la definición de leakage de 7 a 4 clases**
  (`EMAIL, FAMILY, NAME, ID, PHONE, URL, PROFESSIONAL` → `EMAIL, NAME, PHONE,
  ID`). Esto **sí** ocurrió con resultados a la vista; se neutraliza reportando
  **siempre ambas definiciones** (ver `eval/PROTOCOL.md`).
- `4f0a3d6`: fusión de `NOMBRE_PERSONAL_SANITARIO` y
  `NOMBRE_SUJETO_ASISTENCIA` (y `DOCTOR`) en `NAME`. Es una decisión de
  taxonomía razonable (para seudonimizar, cualquier nombre de persona recibe el
  mismo tratamiento), pero se commiteó **con resultados a la vista**; queda
  justificada por escrito en `eval/PROTOCOL.md` **antes** de la ejecución final.

Lección: ningún cambio de definición de métrica puede hacerse con resultados a
la vista. El protocolo de evaluación (`eval/PROTOCOL.md`) congela definiciones
y particiones antes de medir.

### N2. `code_revision` incoherente con el código que produjo los JSON

`eval/results/meddocan.json` declara `code_revision: 8754c1b9…`, pero fue
generado por un código posterior. Ningún JSON de resultados permite reconstruir
qué código lo produjo. Regla nueva (en `eval/PROTOCOL.md`): cada JSON lleva
`code_revision` = `git rev-parse HEAD` **en el momento de ejecutar**, y un test
marca `"dirty": true` si el árbol no estaba limpio (`git status --porcelain`).

### N3. Confusión ID/PHONE en el detector

En `dev`, la clase ID tiene F1 ≈ 0 con soporte alto (1499) y PHONE tiene
precisión ≈ 2 % con recall alto. La regex de teléfono
(`\b(?:(?:\+|00)\d{1,3}[\s.-]?)?[3456789](?:[\s.-]?\d){8}\b`) absorbe
identificadores (NHC, DNI, CIP, nº de colegiado) que empiezan por dígito y
tienen ≥ 9 cifras. Confirmado por la matriz de confusión gold→pred en la Fase C
(`docs/dev/eval-diagnosis.md`). Corrección en la Fase C: regex de teléfono
acotada a formatos telefónicos y regex de identificadores con formatos concretos
(DNI/NIE con letra válida, NHC, CIP, SS), con prioridad de la más específica en
el dedup por solape.

### N4. Restauración de placeholders frágil

`deanonymize` usaba `str.replace` exacto y la tabla de robustez de
`eval/results/utility.json` estaba al 0 % en todas las perturbaciones. Corregido
en la Fase D con restauración por regex insensible a mayúsculas y tolerante a
perturbaciones, más un test de propiedad (Hypothesis).

### N5. Exclusión injustificada de Presidio como baseline

La primera pasada excluyó Microsoft Presidio argumentando que "no está alineado
con las guías de MEDDOCAN y rindió mal en CARMEN-I". Ninguna de las dos razones
es válida: un baseline que rinde mal sigue siendo el baseline; la desalineación
de taxonomía se resuelve mapeando al conjunto unificado; y neutralización y
leakage no dependen de la etiqueta. Reintroducido en la Fase F2
(`eval/results/presidio_meddocan.json`).

### N6. `docs/dev/` borrado

La carpeta `docs/dev/` se eliminó tras la primera pasada. Esta pasada la
reescribe desde el estado actual (no la restaura): los enlaces de `README.md`,
`docs/SECURITY.md`, `docs/threat-model.md`, `eval/README.md`, `src/secure.py` y
`eval/common.py` vuelven a resolver (verificado con `grep -rn "docs/dev"`).

---

## 3. Estado consolidado por componente

- **Protocolo v2** (`src/secure.py`): PSK + HKDF-SHA256, claves separadas por
  dirección, AAD canónico, frescura contra reloj del servidor, anti-replay
  fail-closed, respuesta ligada al `req_id`. ADR: `docs/dev/adr-001-protocol.md`.
- **Proxy** (`src/proxy.py`): allowlist `(método, ruta)`, límite de cuerpo,
  timeouts, caches acotados, arranque fail-closed, log con `req_id`/razón/tamaño.
- **Detector** (`src/anonymizer.py`): BERT + regex con taxonomía unificada;
  corregido en la Fase C y congelado en el tag `eval-frozen-v1`.
- **Restauración** (`deanonymize`): reescrita en la Fase D.
- **Evaluación** (`eval/`): protocolo congelado en `eval/PROTOCOL.md`; resultados
  versionados en `eval/results/*.json`.
