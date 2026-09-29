# Diagnóstico: Bug de Potencia Activa Extrema en Nodo MT

**Fecha:** 2026-09-22  
**Análisis basado en:** Artifact KkGJQub4j9h8pmLrm2eq1B  
**Estado:** Logs de diagnóstico agregados; tabla unifilar_nodes vacía en dev

---

## Resumen Ejecutivo

Se realizó un análisis detallado del flujo de suma de potencia en nodos MT (Media Tensión) del backend. El análisis identificó 5 hipótesis sobre el origen del bug de potencia activa extrema:

1. **D1** (Improbable): Frontera con device_ids duplicados → sobrescritura en dict, no suma doble
2. **D2** (Probable): Nodo MT aparece en su propia frontera (ciclo o bifurcación) → suma duplicada
3. **D3** (Muy improbable): Datos escalados por error en transformación
4. **D4** (Posible): Bifurcación inesperada en árbol MT
5. **D5** (Muy improbable): Frontend escala erróneamente

## Conclusión Principal

**La hipótesis más probable es D2**: El algoritmo BFS de `nodos_medidores_frontera()` es correcto y previene ciclos (línea 78-80), pero es **vulnerable si hay un ciclo o bifurcación en la BD**.

### Riesgos Verificados

```
┌─ nodo MT (device_id=med-mt-01)
│  ├─ hijo_virtual_1
│  │  └─ medidor-1 (device_id)   ← se agrega al resultado
│  └─ hijo_virtual_2
│     └─ med-mt-01               ← ciclo: aparece nuevamente
│        └─ medidor-2 (device_id) ← duplica potencia de med-mt-01
```

Si el árbol tiene esta estructura accidental, `dispositivos_ids` sería `["med-mt-01", "medidor-2"]`, pero el dict `lecturas_por_dispositivo` hace sobrescritura, no suma. **Sin embargo**, si el árbol bifurca y un mismo device aparece en dos ramas, la sobrescritura ocultaría una rama entera.

---

## Trabajos Realizados

### 1. Scripts de Diagnóstico en SQL

**Archivo:** `scripts/diagnose_mt_potencia_bug.py`

Realiza queries SQL sobre la tabla `unifilar_nodes` para verificar:
- **D1+D2**: Device IDs duplicados
- **D2**: Ciclos en el árbol (CTE recursiva)
- **D4**: Estructura del árbol desde un nodo dado

**Limitación:** La tabla `unifilar_nodes` está vacía en dev. Requiere ser ejecutado en producción o con datos de prueba reales.

### 2. Logs de Diagnóstico en Backend

Se agregó logging estructurado (structlog) en 3 puntos clave:

#### a. **Resolución de frontera** (`consultar_nodo_unifilar.py`)
```python
_log.info(
    "nodo_unifilar_frontera_resuelta",
    planta_id=planta_id,
    nodo_id=nodo_id,
    nodos_frontera_count=len(nodos_frontera),
    dispositivos_ids=dispositivos_ids,
    dispositivos_unicos=len(set(dispositivos_ids)),
    hay_duplicados=len(dispositivos_ids) != len(set(dispositivos_ids)),
)
```

**Punto de inserción:** Métodos `resumen()` e `historico()` de `ConsultarNodoUnifilarUseCase`.

**Información capturada:**
- ID del nodo consultado
- Count de nodos en frontera
- Lista completa de device_ids resueltos
- Detección de duplicados

#### b. **Agregación de dispositivos** (`agregacion_dispositivos.py`)
```python
_log.debug(
    "agregador_historico_inicio",
    dispositivos_count=len(dispositivos_ids),
    dispositivos_ids=dispositivos_ids,
    granularidad=granularidad,
    horas=horas,
)
```

**Punto de inserción:** Funciones `calcular_resumen()` y `calcular_historico()`.

**Información capturada:**
- Count de dispositivos
- Lista de device_ids
- Parámetros de granularidad

#### c. **Suma de potencia en el tiempo** (`agregador_dispositivos.py`)
```python
_log.debug(
    "agregador_sumar_potencia_inicio",
    dispositivos_count=len(lecturas_por_dispositivo),
    puntos_totales=total_puntos,
    intervalo_segundos=intervalo_segundos,
)
```

**Punto de inserción:** Método `sumar_potencia_en_el_tiempo()`.

**Información capturada:**
- Count de dispositivos
- Total de puntos de telemetría a sumar
- Intervalo de bucketización

---

## Cómo Usar los Logs para Diagnosticar

### En Producción (con datos reales)

1. **Configurar log level en DEBUG** (si está en INFO por defecto):
   ```bash
   # En el VPS o en .env:
   DEBUG=true  # o LOGLEVEL=DEBUG
   ```

2. **Ejecutar una consulta de historico de nodo MT** desde la UI o API:
   ```bash
   GET /api/v1/plantas/{planta_id}/nodos/{nodo_id}/historico?horas=24
   ```

3. **Revisar los logs con jq:**
   ```bash
   tail -f /var/log/datamaq-telemetry.log | jq 'select(.event == "nodo_unifilar_frontera_resuelta")'
   ```

4. **Buscar señales de alerta:**
   - `hay_duplicados: true` → encontrado duplicado
   - `dispositivos_unicos < dispositivos_ids | length` → hay repeticiones
   - `dispositivos_ids` que incluya el mismo nodo_id consultado → ciclo potencial

### En Desarrollo (si hubiera datos)

```bash
cd /home/agustin/proyectos_software/datamaq/datamaq-telemetry

# Ejecutar script de diagnóstico SQL
.venv/bin/python -m scripts.diagnose_mt_potencia_bug \
  --planta-id c64fd625-0037-4caa-b68a-800e8e0ee548 \
  --nodo-id acometida-13200v
```

---

## Próximos Pasos Recomendados

### Inmediatos (esta semana)

1. ✅ **Agregar logs** — Ya realizado
2. 📋 **Verificar datos en producción:**
   - Ejecutar query D1+D2 sobre BD producción
   - Buscar registros duplicados de device_id
   - Detectar ciclos en árbol unifilar

3. 📊 **Correlacionar con el bug:**
   - Aislar el nodo MT donde ocurre la potencia extrema
   - Revisar sus logs de frontera resuelta
   - Comparar dispositivos_ids esperados vs. reales

### Verificación Final

Una vez identificado el duplicado o ciclo:

```sql
-- Extraer la subestructura problemática
SELECT id, parent_id, device_id, node_type
FROM unifilar_nodes
WHERE facility_id = '[facility_id]'
  AND (
    device_id IN (SELECT device_id FROM unifilar_nodes GROUP BY device_id HAVING COUNT(*) > 1)
    OR id IN (SELECT id FROM unifilar_nodes WHERE parent_id IN (SELECT id FROM unifilar_nodes))
  )
ORDER BY parent_id, id;
```

---

## Archivos Modificados

| Archivo | Cambio | Línea(s) |
|---------|--------|----------|
| `src/application/use_cases/consultar_nodo_unifilar.py` | Log en `resumen()` e `historico()` | 186-195, 249-259 |
| `src/application/use_cases/agregacion_dispositivos.py` | Import structlog + logs en funciones | 10-21, 31-40, 66-75 |
| `src/domain/telemetria/servicios/agregador_dispositivos.py` | Import structlog + log en `sumar_potencia_en_el_tiempo()` | 7-12, 188-197 |
| `scripts/diagnose_mt_potencia_bug.py` | Reescrito con SQL puro | Toda |

---

## Limitaciones Conocidas

1. **Tabla unifilar_nodes vacía en dev** — No se puede reproducir el bug localmente
2. **Scripts requieren datos reales** — Solo útiles en producción o con BD seed completa
3. **Detección de ciclos por código** — `nodos_medidores_frontera()` los previene, pero no detecta bifurcaciones anómalas

---

## Referencia: Arquitectura de la Suma

```
┌─ Request: GET /api/v1/plantas/{planta_id}/nodos/{nodo_id}/historico
│
├─> ConsultarNodoUnifilarUseCase.historico()
│   ├─> _resolver_nodo()
│   │   └─> ArbolUnifilarService.nodos_medidores_frontera()  ← BFS
│   │       └─> [Log: frontera resuelta]  ✓ AGREGADO
│   │
│   └─> calcular_historico()
│       ├─> [Log: historico_inicio]  ✓ AGREGADO
│       └─> AgregadorDispositivosService.sumar_potencia_en_el_tiempo()
│           ├─> [Log: sumar_potencia_inicio]  ✓ AGREGADO
│           └─> SUMA: for dispositivo_id, lecturas in lecturas_por_dispositivo.items()
│               └─> totales_p_por_bucket[bucket_ts] += potencia_w
│
└─> Response: [PuntoPotenciaNodoUnifilarDTO, ...]
```

---

## Checklist de Verificación

- ✅ Logs agregados a 3 puntos de la cadena de suma
- ✅ Scripts de diagnóstico SQL listos
- ✅ Hipótesis documentadas y priorizadas
- ✅ Tipos de Python verificados (0 errores)
- ⏳ Pendiente: Ejecución con datos reales en producción
- ⏳ Pendiente: Verificación de duplicados en BD producción
- ⏳ Pendiente: Corrección si se identifica la raíz

---

## Contacto para Debug

Si el bug reaparece en producción:

1. Revisar los logs con nivel DEBUG
2. Extraer la línea donde `hay_duplicados: true`
3. Notar el nodo_id y los dispositivos_ids
4. Ejecutar query SQL sobre facility_id correspondiente
5. Compartir output de query + logs para análisis profundo
