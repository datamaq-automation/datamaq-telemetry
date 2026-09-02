# Spec: Purga de Telemetría por Rango Temporal (`corte_hasta`)

## 1. Objetivo y Contexto

Dotar al flujo de purga de un modo de **corte por timestamp explícito** además
de la retención por días vigente. Necesario para el saneamiento de producción
del 2026-09-01: eliminar la telemetría **mock** (historial de prueba de la UI)
persistida en `datamaq_telemetry` antes de que el medidor real `Powermeter-3564`
(`D48C49F03564`) comenzara a publicar, **sin** tocar los datos reales.

**Frontera verificada en producción (UTC):** el primer registro real es
`2026-09-01 21:40:04`. Todo lo anterior es mock:

| Tabla | Mock (`recorded_at < 21:40:04`) | Real (desde 21:40:04) |
|---|---|---|
| `telemetry_energy` | 245 | 117 |
| `telemetry_instantaneous` | 116 | 57 |
| `device_status_logs` | a confirmar en ejecución | — |

**Alcance:** campo nuevo `corte_hasta` en `PurgaRequestDTO`, rama nueva en
`PurgarTelemetriaExpiradaUseCase`, flag `--hasta` en el CLI
`scripts/purge_telemetry.py` y validación de corte futuro. **No** se modifican
los puertos ni los repositorios: los métodos `purgar_*_anteriores_a(fecha_limite)`
ya aceptan una fecha arbitraria.

## 2. Dominio y Puertos

### `src/domain/telemetria/exceptions.py`

- `CortePurgaFuturoError(DominioTelemetriaException)` — se lanza cuando
  `corte_hasta` es posterior al instante actual. Sin lógica de terceros; herencia
  pura de la excepción base del dominio.

### `src/domain/telemetria/ports.py` (sin cambios)

Se reutilizan tal cual:

- `purgar_instantaneas_anteriores_a(fecha_limite, batch_size) -> int`
- `purgar_energias_anteriores_a(fecha_limite, batch_size) -> int`
- `purgar_status_logs_anteriores_a(fecha_limite, batch_size) -> int`
- `purgar_alertas_resueltas_anteriores_a(fecha_limite, batch_size) -> int`

## 3. Casos de Uso y DTOs

### `src/application/dtos/purga_dto.py`

```python
class PurgaRequestDTO(BaseModel):
    dias_retencion_override: int | None = None
    corte_hasta: FechaHoraUTC | None = None   # NUEVO
    batch_size: int = 1000
```

- `FechaHoraUTC` normaliza cualquier datetime entrante a UTC *aware* (naive ⇒ UTC).

### `src/application/use_cases/purgar_telemetria.py`

`PurgarTelemetriaExpiradaUseCase.ejecutar(dto)`:

1. Si `dto.corte_hasta is not None`:
   - Validar `corte_hasta <= ahora`; si es futuro ⇒ `CortePurgaFuturoError`.
   - `corte_telemetria = corte_logs = corte_alertas = corte_hasta`.
2. Si `dto.corte_hasta is None`: comportamiento actual intacto
   (7 días telemetría/logs, 30 días alertas resueltas).
3. Drenado por lotes idéntico al actual (sin cambios).

### `scripts/purge_telemetry.py` (CLI)

- Función pura `parsear_corte_hasta(valor: str) -> datetime`:
  `datetime.fromisoformat`; si es naive ⇒ `replace(tzinfo=timezone.utc)`.
  Valor inválido ⇒ `ValueError`.
- Flag `--hasta "YYYY-MM-DD HH:MM:SS"` (UTC si no trae offset).

## 4. Matriz de Pruebas (RED Suite)

Fichero: `tests/unit/test_purga_rango.py` (usa `SpyTelemetriaRepo` heredado de
`MockTelemetriaRepo` que registra las fechas límite recibidas).

**Gherkin**

```gherkin
Escenario: Purga con corte explícito
  Dado un repo sin registros
  Y un corte_hasta = 2026-09-01 21:40:04 UTC
  Cuando ejecuto la purga con ese corte
  Entonces los 4 métodos purgar_*_anteriores_a reciben exactamente ese corte

Escenario: Purga sin corte conserva retención por días
  Dado un repo sin registros
  Y un PurgaRequestDTO sin corte_hasta
  Cuando ejecuto la purga
  Entonces las fechas límite quedan en el pasado (retención 7/30 días)

Escenario: Corte futuro rechazado
  Dado un corte_hasta posterior a "ahora"
  Cuando ejecuto la purga
  Entonces se lanza DominioTelemetriaException (CortePurgaFuturoError)

Escenario: Parseo del flag --hasta (CLI)
  Dado el string "2026-09-01 21:40:04" (naive)
  Cuando llamo parsear_corte_hasta
  Entonces devuelve datetime aware UTC igual al corte
  Y "2026-09-01T21:40:04+00:00" produce el mismo valor
  Y un formato inválido lanza ValueError
```

Contratos de test (assertions):

- `test_purga_con_corte_hasta_usa_esa_fecha`
- `test_purga_sin_corte_hasta_conserva_retencion_por_dias`
- `test_purga_corte_hasta_futuro_es_rechazado`
- `test_parsear_corte_hasta_naive_asume_utc`
- `test_parsear_corte_hasta_con_offset_utc`
- `test_parsear_corte_hasta_formato_invalido`

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` (integridad, ruff, pyright strict, DIP, cobertura ≥ 85%).
- Cero `# type: ignore`, cero re-exportaciones, adaptadores sin `import logging`.
- Cobertura de la nueva rama (corte_hasta presente y ausente) y del parser CLI.
