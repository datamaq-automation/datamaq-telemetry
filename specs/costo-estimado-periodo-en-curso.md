# Spec: Costo monetario estimado del período en curso

> **Estado:** implementado (componente de energía) · **Fecha:** 2026-09-27
> **Decisiones aplicables:** `decisions/2026-09-27_costo-estimado-periodo-en-curso.md` (repo padre)
> **Repos afectados:** `datamaq-telemetry` (este bloque), `app-datamaq`

## 1. Objetivo y Contexto

**Objetivo:** exponer el costo estimado en pesos del período de facturación en curso de una
planta, separado en componente de energía (implementado) y componente de potencia (bloqueado,
"s/d" explícito).

**Ya hecho por el padre (no repetir):** decisión con D1-D5 respondidas
(`decisions/2026-09-27_costo-estimado-periodo-en-curso.md`); certeza de que no había conflicto de
modelos de factura (reconciliación cerrada en `TODO.md` del repo padre, 2026-09-27) — el DTO
`FacturaDistribuidoraResponseDTO` ya es por-documento (energía O potencia, nunca ambas).

## 2. Dominio & Puertos

Sin cambios de dominio: se reutiliza `FacturaDistribuidora` (`src/domain/sge/entities.py`) para el
`$/kWh` promedio, y `ArbolUnifilarService.medidores_frontera` (`src/domain/telemetria/servicios/`)
para resolver los medidores del nodo (mismo patrón que `ConsultarBalanceEnergiaUseCase` y
`ConsultarNodoUnifilarUseCase`). No se agregaron puertos nuevos.

## 3. Casos de Uso & DTOs

- **`ConsultarCostoEstimadoUseCase`** (`src/application/use_cases/consultar_costo_estimado.py`):
  - Resuelve el nodo (por defecto, el primer TGBT/Transformador de la planta, o la raíz si no hay
    ninguno — mismo criterio que `ConsultarBalanceEnergiaUseCase`) y sus medidores frontera.
  - **kWh del período en curso:** reutiliza `calcular_resumen` (ya usado por
    `ConsultarNodoUnifilarUseCase`) con granularidad `"month"` y ventana de 60 días, y toma el
    delta del mes calendario en curso (zona `America/Argentina/Buenos_Aires`, mismo criterio de
    período que usan las facturas `"YYYY-MM"`). `None` si no hay medidores o no hay dato del mes
    en curso todavía (nunca `0`, D1).
  - **`$/kWh` promedio:** de la última `FacturaDistribuidora` con `tipo_dato="energia"` de la
    planta (mismo fallback que `ConsultarBalanceEnergiaUseCase`).
  - **Costo de energía** = kWh en vivo × `$/kWh` promedio. `None` si falta cualquiera de los dos
    factores — nunca un número parcial (D1).
  - **Aviso de tarifa desactualizada (D4):** `true` si pasaron más de 35 días desde el cierre del
    período de la factura de origen.
  - **Componente de potencia:** siempre `costo_potencia_ars=None` con
    `motivo_potencia_sin_dato="demanda_maxima_no_disponible"` — requiere tracking de demanda
    máxima del período en curso sobre datos en vivo, que no existe (gap detectado por el padre,
    es la pieza de mayor esfuerzo). **No implementado en este bloque.**
- **`CostoEstimadoResponseDTO`** (`src/application/dtos/sge_dto.py`): `plantaId`, `periodoActual`,
  `kwhConsumidoPeriodoActual`, `valorEnergiaArsKwhPromedio`, `costoEnergiaArs`,
  `periodoFacturaOrigen`, `avisoTarifaDesactualizada`, `costoPotenciaArs` (siempre `null` por
  ahora), `motivoPotenciaSinDato`.
- **Endpoint:** `GET /api/v1/sge/plantas/{planta_id}/costo-estimado?nodo_id=` (opcional), protegido
  por `resolver_planta_permitida` (mismo aislamiento que el resto de `sge_router.py`).

## 4. Matriz de Pruebas

`tests/unit/test_consultar_costo_estimado_uc.py` (7 tests, mocks de repos/telemetría):

- Costo de energía = kWh en vivo × `$/kWh` promedio de la última factura.
- Componente de potencia siempre `None` con motivo explícito.
- Sin factura de energía → costo `None` (no `0`).
- Sin nodos/medidores → kWh `None`.
- Aviso de tarifa desactualizada con factura vieja (>35 días).
- Sin facturas → sin aviso (no hay tarifa que comparar).
- `periodoActual` con formato `YYYY-MM`.

Gauntlet verificado 2026-09-27: 1538 unit + 4 skipped, `ruff check .` limpio, `pyright` 0 errores,
`verify_architecture.py` y `verify_code_size.py` en verde.

## 5. Criterios del Gauntlet

- [x] Arquitectura: dominio sin dependencias nuevas de terceros; caso de uso solo importa de
  `domain/` y reutiliza helpers de `application/use_cases/agregacion_dispositivos.py`.
- [x] Tipos: `pyright` 0 errores en los archivos nuevos/modificados.
- [x] Tests unitarios en verde, cobertura del caso de uso nuevo.
- [ ] **Pendiente, fuera de este bloque:** componente de potencia (tracking de demanda máxima en
  vivo) — bloque separado a futuro, no bloquea el cierre de este.
- [ ] **Pendiente:** `app-datamaq` consume el endpoint (tarjeta/indicador en `features/facturas/`).
- [ ] **Verificación cruzada del padre:** `curl` en producción tras el deploy.

**Traspasada a hija:** sí (esta es la spec hija, ya completa) · **Bloque cerrado:** parcial —
componente de energía cerrado, componente de potencia queda como bloque futuro separado.
