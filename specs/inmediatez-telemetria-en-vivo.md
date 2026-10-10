# Inmediatez de telemetría en vivo (Fase 1: broadcast DTO normalizado)

## 1. Objetivo y Contexto

El canal WebSocket `/ws/live` no entrega datos en vivo de amperaje/potencia cuando el
medidor publica el formato compacto de raíz (`{"n":"R","v":...,"i":...,"p":...,"q":...}`),
propio de los medidores monofásicos 1P2W.

**Causa raíz:** `IngestarTelemetriaUseCase.ejecutar` publica en el topic `inst` el
payload crudo recibido del MQTT, en lugar del DTO normalizado. El frontend no sabe
parsear el formato de raíz y descarta el mensaje, por lo que la pantalla de consumo
queda congelada hasta la próxima consulta REST.

**Alcance de esta fase (solo backend):**
- El topic `inst` debe difundir en vivo el `LecturaInstantaneaDTO` normalizado
  (mismo contrato que el endpoint REST `/api/.../instantaneas?limite=1`), incluyendo
  `analitica`, `fase_r/s/t` y totales.
- Los subtopics distintos de `inst` (`acc`, `energyio`, `status`, `event`) conservan
  el broadcast crudo tal cual llega.
- No se modifican entidades, puertos ni el router WS de infraestructura.

**Fuera de alcance (fases siguientes):** parser root-n del frontend, indicador de
edad de lectura y manejo de 403 del WS.

## 2. Dominio & Puertos

Sin cambios en `src/domain/`. Se reutiliza el puerto existente:

- `PublicadorEventosPort.publicar_telemetria_en_vivo(topico, datos)`.
- Entidad `LecturaInstantanea` y mapeo `TelemetriaMapper.instantanea_to_dto(lectura)`.

## 3. Casos de Uso & DTOs

### 3.1 IngestarTelemetriaUseCase (ajuste en `ejecutar`)

Flujo modificado:

1. Parsear `topico` en `mac_raw` y `subtopico` ANTES del broadcast (mover el guard
   `len(partes) < 4` al inicio, como ya ocurre en el resto del método).
2. Si hay publicador y `subtopico != "inst"`: difundir `payload` crudo (comportamiento
   actual conservado para `acc`, `energyio`, `status`, `event`).
3. En la rama `inst`, tras construir `lectura` (antes de la evaluación de alertas),
   difundir `TelemetriaMapper.instantanea_to_dto(lectura).model_dump(mode="json")`.

El DTO emitido por `inst` incluye:

- `fase_r`, `fase_s`, `fase_t` con claves extendidas (`voltage_V`, `current_A`,
  `net_active_power_W`, `net_reactive_power_VAR`, `net_apparent_power_VA`,
  `power_factor`, `thd_v_pct`, `thd_i_pct`).
- Totales: `potencia_activa_total_W`, `potencia_reactiva_total_VAR`,
  `potencia_aparente_total_VA`, `factor_potencia_total`.
- `analitica` (computada por `calcular_analitica_completa`).

## 4. Matriz de Pruebas (RED Suite)

Archivo: `tests/unit/test_inmediatez_ws.py`.

### Escenario 1: `inst` con formato raíz publica DTO normalizado

```gherkin
Dado un dispositivo 1P2W con fases_con_ti "R" registrado
Y un payload compacto {"t":1788303000,"n":"R","v":227.7,"i":0.9,"p":147,"q":-51}
Cuando ejecuto "m/wifi/D48C49F03564/inst"
Entonces el publicador recibe EXACTAMENTE un evento en "m/wifi/D48C49F03564/inst"
Y ese evento es el DTO (tiene "fase_r" con voltage_V==227.7, current_A==0.9, net_active_power_W==147.0)
Y no es el payload crudo (no contiene la clave "n" en la raíz)
```

### Escenario 2: subtopic distinto de `inst` conserva payload crudo

```gherkin
Dado un use case con permitir_auto_registro=False y un mac desconocido
Y un payload {"timestamp":1788303000,"x":1}
Cuando ejecuto "m/wifi/UNKNOWNMAC/acc"
Entonces el publicador recibe el payload crudo íntegro en "m/wifi/UNKNOWNMAC/acc"
```

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh`: integridad, `ruff check .`, `ruff format --check .`, `pyright`.
- `agy-opt audit-dip`: 0 violaciones.
- `.venv/bin/pytest tests/unit/ --cov=src --cov-fail-under=85`: 100% verde, cobertura >= 85%.
