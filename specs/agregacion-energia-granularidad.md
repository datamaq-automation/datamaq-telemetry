# Spec: Agregación de Energía por Periodo (`granularity=day|month`)

## 1. Objetivo y Contexto

El gráfico «Energía activa» del frontend consume `GET /api/telemetria/energy/{device_id}`,
que hoy devuelve **registros crudos** del contador acumulado (`AcumuladoEnergiaDTO`),
uno por lectura. Con el medidor real publicando cada ~2.5 min, la UI dibuja una barra
por registro (todas con la misma fecha local) y un «Consumo Total» que es la suma de
acumulados — valores sin significado de consumo.

**Objetivo:** exponer el **consumo de energía por periodo** (día o mes) calculado como
**delta** del contador acumulado entre periodos consecutivos, en zona horaria configurable
(default `America/Argentina/Buenos_Aires`), para que la UI dibuje 1 barra por día/mes
con el consumo real del periodo.

**Regla de negocio:**
- `energia(periodo_n) = último_acumulado(periodo_n) − último_acumulado(periodo_{n-1})`.
- El **primer** periodo (sin referencia anterior) devuelve `energia_activa_neta_kwh: null`;
  la UI no dibuja barra para ese periodo.

**Alcance:** valor `day`/`month` para la granularidad, query `timezone`, DTO
`EnergiaAgregadaDTO`, rama nueva en el caso de uso y método nuevo en el repositorio.
El valor por defecto `raw` conserva el contrato actual **intacto** (backward compatible).

## 2. Dominio y Puertos

### `src/domain/telemetria/value_objects.py`

- `GranularidadEnergia(str, Enum)` — `DIA = "day"`, `MES = "month"`.

### `src/domain/telemetria/entities.py`

- `EnergiaAgregada` (dataclass frozen): `periodo: date`, `energia_activa_neta_kwh: float | None`.
  `None` = primer periodo sin referencia (se omite en la UI).

### `src/domain/telemetria/services.py`

- `AgregacionEnergiaService.agregar_por_periodo(acumulados, granularidad, zona) -> list[EnergiaAgregada]`:
  1. Ordena los acumulados por `registrado_en` ascendente (independiente del orden del repo).
  2. Descarta registros sin `energia_activa_neta`.
  3. Agrupa por periodo en la zona (`day` → `fecha local`; `month` → primer día del mes local).
  4. Toma el **último** acumulado de cada periodo.
  5. Calcula el delta respecto del periodo anterior; primer periodo → `None`.
  - Puro (stdlib + `zoneinfo`), sin librerías de terceros.

### `src/domain/telemetria/ports.py`

- `RepositorioTelemetriaPort.listar_acumulados_para_agregacion(dispositivo_id, desde) -> list[AcumuladoEnergia]`:
  crudos del rango en orden cronológico ascendente, sin límite.

### `src/domain/telemetria/exceptions.py`

- `GranularidadEnergiaInvalidaError(DominioTelemetriaException)` — granularidad fuera de `day|month`.
- `ZonaHorariaInvalidaError(DominioTelemetriaException)` — timezone IANA inválido.
  (Ambas heredan de `DominioTelemetriaException` ⇒ mapean a HTTP 422 vía `ErrorPresenter`.)

## 3. Casos de Uso y DTOs

### `src/application/dtos/telemetria_dto.py`

```python
class EnergiaAgregadaDTO(BaseModel):
    periodo: date
    energia_activa_neta_kwh: float | None = None
    model_config = ConfigDict(from_attributes=True)
```

- `date` serializa como `YYYY-MM-DD`.

### `src/application/mappers/telemetria_mapper.py`

- `TelemetriaMapper.energia_agregada_to_dto(EnergiaAgregada) -> EnergiaAgregadaDTO`.

### `src/application/use_cases/consultar_telemetria.py`

`ConsultarTelemetriaUseCase.listar_energia_agregada(id_o_uid, granularidad, zona, dias)`:
1. Resuelve dispositivo y acota `desde` con la política de retención (como `listar_energias`).
2. Valida `granularidad` (`GranularidadEnergia`) y `zona` (`ZoneInfo`); valor inválido ⇒
   `GranularidadEnergiaInvalidaError` / `ZonaHorariaInvalidaError`.
3. Obtiene crudos vía `listar_acumulados_para_agregacion`.
4. Delega en `AgregacionEnergiaService` y mapea a `EnergiaAgregadaDTO`.

### `src/infrastructure/fastapi/routes/telemetria_router.py`

`GET /energy/{device_id}` gana:
- `granularity: Literal["raw","day","month"] = "raw"` (validación automática 422).
- `timezone: str = "America/Argentina/Buenos_Aires"`.
- `raw` ⇒ comportamiento actual; `day`/`month` ⇒ `listar_energia_agregada`.
- `response_model=list[AcumuladoEnergiaDTO | EnergiaAgregadaDTO]`.

### `src/infrastructure/sqlalchemy/mysql_repositories.py`

- `MySQLTelemetriaRepository.listar_acumulados_para_agregacion`: `ORDER BY recorded_at ASC`.

## 4. Matriz de Pruebas (RED Suite)

Fichero unitario: `tests/unit/test_agregacion_energia.py`.
Fichero de integración: `tests/integration/test_telemetria_agregacion_api.py`.

```gherkin
Escenario: Agregación diaria con delta
  Dado acumulados los días 1, 2 y 3 (últimos 10, 15, 22 kWh)
  Cuando agrego por día en America/Argentina/Buenos_Aires
  Entonces 3 periodos; día 1 → None, día 2 → 5.0, día 3 → 7.0

Escenario: Agregación mensual con delta
  Dado acumulados en meses distintos
  Cuando agrego por mes
  Entonces periodos = primer día de cada mes y deltas correctos

Escenario: Corte de día en zona local
  Dado un registro 23:30 local y otro 00:30 local del día siguiente
  Cuando agrego por día
  Entonces pertenecen a periodos distintos

Escenario: Primer periodo sin referencia
  Dado un único periodo con datos
  Cuando agrego
  Entonces 1 periodo con energia_activa_neta_kwh None

Escenario: Registros sin acumulado se omiten
  Dado un acumulado con energia_activa_neta None
  Cuando agrego
  Entonces no produce periodo

Escenario: Orden independiente del repo
  Dado acumulados desordenados
  Cuando agrego
  Entonces la serie queda ascendente

Escenario: Caso de uso devuelve DTOs
  Dado un repo con acumulados
  Cuando llamo listar_energia_agregada
  Entonces devuelve EnergiaAgregadaDTO ordenados

Escenario: Granularidad inválida
  Cuando llamo con granularidad "week"
  Entonces lanza GranularidadEnergiaInvalidaError (y el endpoint responde 422)

Escenario: Zona horaria inválida
  Cuando llamo con timezone "No/Existe"
  Entonces lanza ZonaHorariaInvalidaError (y el endpoint responde 422)
```

Contratos (assertions):
- `test_agregacion_dia_calcula_delta_entre_dias`
- `test_agregacion_mes_calcula_delta_entre_meses`
- `test_corte_dia_en_zona_argentina`
- `test_primer_periodo_sin_referencia_es_none`
- `test_registros_sin_acumulado_se_omiten`
- `test_orden_independiente_del_repo`
- `test_listar_energia_agregada_devuelve_dtos`
- `test_listar_energia_agregada_granularidad_invalida`
- `test_listar_energia_agregada_zona_invalida`
- `test_get_energy_aggregated_day_end_to_end` (integración)
- `test_get_energy_granularity_invalida_422` (integración)

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` (integridad, ruff, pyright strict, DIP, cobertura ≥ 85%).
- `./scripts/ci.sh` (integración incluida).
- Cero `# type: ignore`, cero re-exportaciones, adaptadores sin `import logging`.
- Cobertura de la rama agregada (`day`, `month`, `raw`) y de las validaciones.
