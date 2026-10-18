# Spec — Issue #18: pico falso de 22 811 kW en Durax

> Borrador de verificación. Sin commit. Rama `fix/issue-18-pico-delta-energia-hueco` desde `origin/main` (462cf34).
> `spec.md` de la raíz pertenece a otra spec (planes freemium) y no se toca.

## 1. Causa: NO VERIFICADA en `src/`

La hipótesis del Issue (un cálculo deriva kW de `Δ energía / intervalo` y el hueco de 41,5 h da 52 min) **no se encontró en el código**.

Búsquedas hechas en `src/` y `scripts/`:

- **Derivación de potencia desde `telemetry_energy`:** ninguna. Las únicas lecturas del acumulado son:
  - `src/domain/telemetria/servicios/calculos_potencia.py:84-117`: delta entre acumulados por periodo (día/mes), en **kWh**, sin dividir por tiempo.
  - `src/application/use_cases/ingestar_telemetria.py:249`: solo logging.
  - `src/infrastructure/sqlalchemy/repositories/telemetria_repository.py:244-251, 296-353`: lectura del acumulado.
- **Demanda cuartohoraria** (`src/domain/telemetria/servicios/calculador_demanda_cuartohoraria.py:50-80`, `src/application/use_cases/agregacion_dispositivos.py:173-215`): toma `potencia_activa_total_w / 1000` ya agregada, **no** un delta de energía.
- **Potencia bucketizada SQL** (`telemetria_repository.py:481-520`): `AVG(total_active_power)` de la tabla **instantánea**, con `es_dato_confiable`. No usa `telemetry_energy`.
- **Conversiones kWh↔kW con tiempo** (`src/domain/cargas/value_objects.py:302`, `src/domain/cargas/servicios/atribuidor_consumo.py:46`): van en sentido **kW·h → kWh** (potencia media × duración), no al revés, y pertenecen al dominio de cargas, no a Durax.
- **Scripts:** `scripts/mock_telemetry.py` genera energía a partir de potencia (no al revés).

**Consecuencia:** el pico de 22 811 kW no sale de ningún cálculo del backend que se pueda reproducir con datos de `src/`. Como el máximo instantáneo real es 574 kW (Issue), el valor tampoco sale de la tabla instantánea. Queda fuera de `src/` (candidatos a verificar, sin tocar producción): código de `app-datamaq` (frontend que derive kW del acumulado), un MCP/tool externo o una consulta ad hoc.

## 2. Criterio de aceptación (propuesto, pendiente de la causa)

- Un hueco de datos de 41,5 h seguido de un salto de energía de 19 780 kWh **no** produce una potencia derivada mayor que `19 780 / 41,5 ≈ 477 kW` (potencia media del hueco) ni mayor que el máximo real de muestras (574 kW).
- Datos continuos: el resultado no cambia respecto de hoy.

Hoy no hay función que cumpla "potencia derivada" en `src/`, así que el criterio no es testeable contra un código que no existe. **Bloqueado hasta confirmar la causa.**

## 3. Matriz de tests RED (pendiente)

| # | Fixture (versionado, sin BD) | Esperado | Estado |
|---|---|---|---|
| T1 | Hueco 41,5 h + salto 19 780 kWh | potencia derivada ≤ 477 kW y ≤ 574 kW | sin función objetivo |
| T2 | Muestras continuas cada 15 min | sin cambio vs. hoy | sin función objetivo |

No se escribió ningún test: no hay código objetivo que lo haga fallar por la razón correcta.

## 4. Pedido al padre

1. Confirmar si el 22 811 kW se observó en **app-datamaq** (cálculo en cliente) o en un tool MCP. La verificación de origen se hace desde esas sesiones, no en el backend.
2. Con esa respuesta, reabro esta spec con el archivo:línea del fix.
3. No codifico hasta tu aprobación.
