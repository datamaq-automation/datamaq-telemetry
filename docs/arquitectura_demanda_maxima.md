# Arquitectura: Tracking de Demanda Máxima en Período de Facturación

## Estado Actual (2026-09-30)

**Endpoint:** `/api/v1/sge/consultar-costo-estimado/{planta_id}`

Retorna `costo_potencia_ars=null` con motivo `"demanda_maxima_no_disponible"` (implementado en `ConsultarCostoEstimadoUseCase`, líneas 71-72).

## Problema

El cálculo de costo de potencia requiere **demanda máxima del período de facturación en curso**:
- **Período:** Típicamente mes calendario (ej. septiembre 2026-09-01 a 2026-09-30)
- **Demanda máxima:** Máximo kW medio registrado en ventana de integración (usualmente 15 min)
- **Uso:** Costo = kW_pico × tarifa_potencia ($/kW)

Sin tracking en tiempo real, el valor queda indeterminado hasta que cierre el período.

## Opciones de Diseño

### Opción A: Acumulador en Caché (Recomendada)

**Mecanismo:** Mantener `max(potencia_adquirida_...)` acumulado en memoria (caché Redis o in-process).

**Flujo:**
1. **Ingesta MQTT** (`IngestarTelemetriaUseCase`): Al registrar potencia de un medidor, actualizar `demanda_max[planta_id][periodo_mes]`
2. **Consulta costo** (`ConsultarCostoEstimadoUseCase`): Leer el acumulado de caché, multiplicar por tarifa
3. **Cierre de período:** Persistir `demanda_max` histórico en tabla MySQL para auditoría; limpiar caché

**Ventajas:**
- Latencia baja (lectura O(1))
- Refleja datos reales en vivo
- No requiere batch jobs nocturnos

**Desventajas:**
- Caché = estado volátil (pérdida si restart)
  - *Mitigación:* Persistir acumulador cada N horas (batch asincrónico)

### Opción B: Precalc Nightly (Más Seguro)

**Mecanismo:** Job nocturnos (ej. 3 AM BsAs) que ejecutan:
```sql
SELECT 
  planta_id,
  DATE_FORMAT(timestamp, '%Y-%m') AS periodo,
  MAX(potencia_adquirida_kw) AS demanda_maxima
FROM telemetria
WHERE DATE_FORMAT(timestamp, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')
  AND planta_id = ?
GROUP BY planta_id, periodo
```

**Flujo:**
1. **Nightly batch:** Calcular `max(potencia)` por planta/período
2. **Persistir:** Tabla `demanda_maxima_periodo` con (planta_id, periodo, valor_kw, calculado_en)
3. **Consulta costo:** Leer de tabla `demanda_maxima_periodo`

**Ventajas:**
- Durabilidad garantizada
- Sin riesgo de volatividad de caché
- Auditable (registra cuándo se calculó)

**Desventajas:**
- Latencia: datos con retraso de ~1 día
- Job adicional en systemd/cron
- Requiere tabla nueva y índices

## Decisión Propuesta

**Híbrido (Opción A + B):**
1. Mantener acumulador en caché (Redis o `demanda_max_periodo_cache` en proceso) durante el período
2. Job nightly: Persistir acumulado en tabla histórica `demanda_maxima_periodo`
3. Fallback: Si caché está vacío, consultar tabla histórica (sirve tras restart)

## Implementación Estimada

| Componente | LOC | Duración |
|---|---|---|
| Servicio de caché de demanda máxima | 50–80 | ~2h |
| Hook de ingesta MQTT | 10–15 | ~1h |
| Job nightly (systemd) | 40–60 | ~2h |
| Tests unitarios (caché + ingesta) | 80–120 | ~3h |
| Tests integración (e2e) | 60–90 | ~3h |
| **Total** | **~300** | **~11h** |

## Índices SQL Necesarios

```sql
CREATE TABLE demanda_maxima_periodo (
  planta_id VARCHAR(36) NOT NULL,
  periodo DATE NOT NULL,  -- 2026-09-01
  demanda_kw DECIMAL(8,2),
  calculado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (planta_id, periodo)
);
CREATE INDEX idx_demanda_planta ON demanda_maxima_periodo(planta_id);
```

## Referencias

- **Decisión:** `decisions/2026-09-27_costo-estimado-periodo-en-curso.md` (D1–D5)
- **Spec activa:** `specs/costo-estimado-periodo-en-curso.md`
- **Use case:** `src/application/use_cases/consultar_costo_estimado.py` (líneas 26–73)
- **Endpoint:** `GET /api/v1/sge/consultar-costo-estimado/{planta_id}`
