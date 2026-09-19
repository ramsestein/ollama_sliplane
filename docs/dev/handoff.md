# Handoff

## Primera pasada (resumen histórico)

Branches por fase, todas con tests en verde:

| Fase | Rama | Head |
|---|---|---|
| 0 | `main` | `53c3aea` |
| 1 | `fase1-protocolo-v2` | `606ccec` |
| 2 | `fase2-proxy` | `84ccf5e` |
| 3 | `fase3-threat-model` | `e10da36` |
| 4 | `fase4-evaluacion` | `f9553d3` |
| 5 | `fase5-empaquetado` | `8d33dd9` |

Qué se hizo: protocol v2, endurecimiento del proxy, poda de whitelist, modelo de
amenazas, arnés de evaluación (`eval/`) y empaquetado SoftwareX. Detalles en
`docs/dev/audit.md`.

## Segunda pasada

Rellenado en la **Fase H** de la segunda pasada. Contiene:

- Qué se cambió en el detector y con qué evidencia de `dev`.
- Comparación antes/después en `dev` y en `test`, distinguiendo qué parte del
  cambio proviene de bugs del arnés corregidos y qué parte de cambios del
  detector.
- Qué frases del manuscrito quedan respaldadas por qué JSON, y qué frases ya no
  se pueden sostener.
- Trabajo futuro priorizado por impacto en leakage.
- Confirmación explícita de que `MEDDOCAN/test` se ejecutó una sola vez, con el
  hash y la fecha.
