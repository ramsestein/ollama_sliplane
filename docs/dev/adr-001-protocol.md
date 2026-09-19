# ADR-001 — Protocol v2: clave pre-compartida con AES-GCM separado por dirección

- **Estado:** aceptado
- **Fecha:** 2026-09-19 (reescrito desde la implementación actual de `src/secure.py`)
- **Sustituye:** protocol v1 (claves rotatorias por ventana temporal + "auth layer")

Este documento describe el protocolo v2 **tal como está implementado hoy** en
`src/secure.py`, no el diseño previo. Diferencias con el diseño v1 se señalan
explícitamente.

## Contexto

El protocol v1 tenía cuatro defectos verificados (ver `docs/dev/audit.md`):

1. Sin comprobación de frescura contra el reloj del servidor: un sobre declaraba
   su propia ventana temporal y `decrypt` aceptaba `window-1`, `window`,
   `window+1` sin comparar con el reloj. Con una caché de replay de 15 minutos,
   todo mensaje capturado era reproducible tras expirar.
2. La "auth layer" derivaba su clave de `SHA-256(model | bert_model | password)`:
   nombres de modelo públicos, sin KDF lento, y la etiqueta GCM actuaba de
   verificador (oráculo de diccionario sobre la contraseña).
3. Todas las claves de ventana derivaban del mismo secreto estático: sin forward
   secrecy ni frescura real.
4. La misma clave se usaba en ambas direcciones sin separación de dominio ni
   ligado petición/respuesta: reflexión posible.

## Decisión

Protocolo **v2**, clave pre-compartida (PSK), construido solo sobre
`cryptography` (AES-256-GCM, HKDF-SHA256):

- **Secreto maestro** `ENCRYPTION_SECRET`: 32 bytes aleatorios en base64. Cliente
  y servidor rechazan valores que no decodifican a ≥ 32 bytes. Generado con
  `python -m src.keygen`.
- **Derivación:** HKDF-SHA256 (`salt=None`) con `info` versionados, una clave por
  dirección:

      c2s = HKDF-SHA256(ikm=secret, info=b"pukara/v2/c2s")
      s2c = HKDF-SHA256(ikm=secret, info=b"pukara/v2/s2c")

  No hay KDF lento: el secreto es una clave aleatoria, no una contraseña humana.
- **Sobre:** `{"v": 2, "ts": <epoch segundos>, "req_id": <16 bytes b64>,
  "nonce": <12 bytes b64>, "ciphertext": <b64>}`. `req_id` y `nonce` son bytes
  aleatorios frescos por mensaje.
- **AAD:** codificación canónica de longitud fija, nunca concatenación de strings:

      b"\x02" + direction_byte + ts.to_bytes(8, "big") + req_id

  con `direction_byte = b"\x01"` (c2s) o `b"\x02"` (s2c). Alterar `v`, `ts` o
  `req_id` invalida la etiqueta GCM.
- **Frescura:** el servidor rechaza `|now − ts| > MAX_SKEW` (120 s por defecto,
  configurable), comparado contra su propio reloj, **después** de verificar la
  etiqueta.
- **Anti-replay:** caché acotada de `req_id` con TTL ≥ 2·MAX_SKEW (siempre mayor
  que la ventana de aceptación) y política fail-closed cuando está llena. La
  comprobación corre después de la verificación de etiqueta.
- **Respuesta:** cifrada con la clave `s2c`; el AAD lleva el `req_id` de la
  petición. El cliente verifica que `req_id` coincide y aplica la misma
  comprobación de frescura.
- **Credenciales:** la auth layer se elimina. La configuración de despliegue del
  cliente (`user`, `password`, `model`, `bert_model`) viaja dentro del payload
  cifrado y se compara con `hmac.compare_digest`. Poseer la PSK ya autentica;
  esta puerta solo fuerza que toda la configuración coincida (los valores nunca
  se usan como material de clave, por lo que no hay oráculo de diccionario).
- **Errores:** una única respuesta genérica para fallos de etiqueta, frescura,
  replay o credenciales; la causa real solo va al log de auditoría (sin oráculo).

## Limitaciones conocidas (documentadas, no ocultas)

- **Sin forward secrecy.** Quien obtenga `ENCRYPTION_SECRET` puede descifrar
  tráfico grabado. Es la limitación honesta del PSK.
- **Sin padding.** Tamaños y tiempos del tráfico son visibles (análisis de
  tráfico no mitigado).
- La seguridad de extremo a extremo depende de que el cliente no esté
  comprometido (conserva el texto original, el mapa y la clave; ver
  `docs/threat-model.md`).

## Alternativa considerada: HPKE / Noise-NK (trabajo futuro)

| Propiedad | PSK-v2 (este ADR) | HPKE / Noise-NK (clave estática de servidor) |
|---|---|---|
| Forward secrecy | No | Sí (DH efímero) |
| Distribución de claves | Un secreto compartido out-of-band | Clave pública del servidor publicada; variantes autenticadas necesitan clave del cliente |
| Replay/frescura | Integrado (`ts` + `req_id`) | Sigue necesitando la misma lógica explícita |
| Dependencias | Solo `cryptography` | Librería HPKE/Noise (dependencia nueva, más código que auditar) |
| Modos de fallo | Robo de PSK descifra tráfico grabado | Robo de clave privada + grabación pasiva descifra tráfico |

HPKE/Noise-NK con clave estática de servidor es el **trabajo futuro** declarado
cuando la falta de forward secrecy se vuelva inaceptable.

## Consecuencias

- v2 rompe v1 sin fallback retrocompatible (un fallback sería vector de
  downgrade). Bump de versión a `0.2.0`, registrado en `CHANGELOG.md`.
- `ENCRYPTION_SECRET` cambia de formato (base64 de ≥ 32 bytes); los secretos
  antiguos se rechazan al arrancar.
- Clientes y servidores deben desplegarse juntos.
