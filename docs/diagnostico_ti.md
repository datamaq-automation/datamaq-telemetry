# Diagnóstico de Transformadores de Intensidad (TI)

## Descripción General

Este documento explica cómo usar los scripts de diagnóstico para validar si la configuración de orden de fases e inversión de TI en un medidor es correcta, basándose en el análisis histórico de datos de telemetría.

## Scripts Disponibles

### 1. `scripts/diagnosticar_ti.py`

**Propósito:** Rankear 6 candidatos de configuración (3 órdenes × 2 polaridades) por coherencia fasorial.

**Uso:**

```bash
.venv/bin/python scripts/diagnosticar_ti.py \
  --device-id c91713f1-0621-4a33-9279-c5327a317d96 \
  --periodo-horas 24 \
  --metrica coherencia \
  --verbose
```

**Parámetros:**

- `--device-id` (obligatorio): UUID del dispositivo
- `--periodo-horas` (default: 24): Horas de histórico a analizar
- `--metrica` (default: "coherencia"): Solo "coherencia" soportada
- `--verbose`: Imprimir detalles

**Salida:**

```
Diagnóstico de TI para TGBT Trafo 2 (ECC9FFB57F20)
Período: 2026-09-26 17:06 a 2026-09-27 17:06 (24h)
Registros analizados: 1440
Fases con TI: R,S

====================================================================================================
 CANDIDATOS RANKEADOS POR COHERENCIA FASORIAL
====================================================================================================
Pos  | Orden Fases     | Invertido  | Score   | Justificación
----------------------------------------------------------------------------------------------------
1    | R,S,T           | NO         | 0.9876  | Error S: 1.2%, Error FP: 0.5%, Q positiva (inductivo)
2    | S,R,T           | NO         | 0.6234  | Error S: 18.3%, Error FP: 22.1%, Q positiva (inductivo)
3    | R,S,T           | SÍ         | 0.0421  | Error S: 95.2%, Error FP: 99.8%, Q negativa (capacitivo)
4    | S,R,T           | SÍ         | 0.0389  | Error S: 96.1%, Error FP: 99.9%, Q negativa (capacitivo)
====================================================================================================

Config actual: R,S, invertido=false
Recomendación: R,S,T (Score: 0.9876)
✓ Candidato 1 es el ACTUAL y tiene coherencia máxima → ESTÁ CORRECTAMENTE CONFIGURADO
```

### 2. `scripts/comparar_ti_bifasico.py`

**Propósito:** Comparar dos medidores para validar que sus configuraciones sean coherentes (opuestas o complementarias).

**Uso:**

```bash
.venv/bin/python scripts/comparar_ti_bifasico.py \
  --device-a 7434647d-5b87-4d4e-b4a5-a0d351315f0a \
  --device-b c91713f1-0621-4a33-9279-c5327a317d96 \
  --fecha-inicio 2026-09-17 \
  --fecha-fin 2026-09-27
```

**Parámetros:**

- `--device-a` (obligatorio): UUID del medidor A (referencia)
- `--device-b` (obligatorio): UUID del medidor B
- `--fecha-inicio` (default: 2026-09-17): Fecha en formato YYYY-MM-DD
- `--fecha-fin` (default: 2026-09-27): Fecha en formato YYYY-MM-DD
- `--verbose`: Detalles

### 3. `scripts/generar_propuesta_ti.py`

**Propósito:** Generar propuesta JSON de corrección para aplicar vía PATCH API.

**Uso:**

```bash
.venv/bin/python scripts/generar_propuesta_ti.py \
  --device-id c91713f1-0621-4a33-9279-c5327a317d96 \
  --candidato-rango 1 \
  --output propuesta.json
```

**Salida (propuesta.json):**

```json
{
  "dispositivo": {
    "id": "c91713f1-0621-4a33-9279-c5327a317d96",
    "uid": "ECC9FFB57F20",
    "ubicacion": "TGBT Trafo 2"
  },
  "propuesta": {
    "orden_fases": ["R", "S", "T"],
    "invertido": false,
    "razon": "Mantener configuración actual (candidato #1, período: 24h)"
  },
  "cambios_respecto_actual": {
    "orden_fases_actual": ["R", "S", "T"],
    "invertido_actual": false,
    "diferencia": "Sin cambios propuestos"
  },
  "curl_para_aplicar": "curl -X PATCH https://api.datamaq.com.ar/api/v1/dispositivos/... -H ..."
}
```

## Métrica: Coherencia Fasorial

La métrica de coherencia valida que la configuración de TI sea interna y fasorialmente consistente.

### Cálculos

Para cada medición de fase y cada candidato, se computan:

1. **Error % en S (Potencia Aparente):**
   - S teórica = √(P² + Q²)
   - Error% = 100 × |S_medida - S_teórica| / S_teórica
   - Mide: coherencia entre mediciones de P, Q y S

2. **Error % en FP (Factor de Potencia):**
   - FP teórico = P / S
   - Error% = 100 × |FP_medida - FP_teórico|
   - Mide: coherencia entre P, S y FP

3. **Score Final:**
   - Score = max(0, 100 - (Err_S% + Err_FP%) / 2) / 100
   - Rango: [0.0 ... 1.0]
   - >0.98: Coherencia máxima (muy probable que sea correcto)
   - >0.70: Coherencia buena (probablemente correcto, validar con patrón certificado)
   - <0.70: Coherencia baja (necesita diagnóstico en campo)

### Signo de Q (Patrón de Carga)

Además del score, se reporta el signo predominante de Q:

- **Q positiva (inductivo):** Dominan cargas rotativas (motores, transformadores)
- **Q negativa (capacitivo):** Dominan bancos de capacitores o generación fotovoltaica
- **Q ≈ 0:** Carga resistiva pura (poco común)

## Árbol de Decisión

```
┌─ Ejecutar: diagnosticar_ti.py
│
├─ ¿Score del candidato #1 > 0.98?
│  ├─ SÍ: Config CORRECTA, DETENER (validación completada)
│  │
│  └─ NO: Pasar a siguiente paso
│
├─ ¿Score del candidato #1 > 0.70?
│  ├─ SÍ: Config PROBABLEMENTE CORRECTA
│  │      → Validar con PATRÓN CERTIFICADO en campo
│  │      → Si patrón coincide: ACEPTAR
│  │      → Si no coincide: Aplicar candidato alternativo
│  │
│  └─ NO: Config PROBABLEMENTE INCORRECTA
│         → Ejecutar: diagnosticar_instalacion_ti.py
│         → Revisar cableado físico en tablero
│         → Ejecutar comparar_ti_bifasico.py si hay medidor de referencia
│         → Evaluar candidatos alternativos (top 2-4)
│
└─ Generar propuesta: generar_propuesta_ti.py --candidato-rango <N>
   → Aplicar propuesta con PATCH API
   → Monitorear 24h y validar Q
```

## Casos de Uso Típicos

### Caso A: Trafo 2 está correctamente configurado

```bash
$ .venv/bin/python scripts/diagnosticar_ti.py \
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \
    --periodo-horas 24

# Resultado: Score 0.9876, Q=+19,000 VAr
# Interpretación: CORRECTO ✓
```

### Caso B: Trafo 1 tiene Q invertida (error potencial)

```bash
$ .venv/bin/python scripts/diagnosticar_ti.py \
    --device-id 7434647d-5b87-4d4e-b4a5-a0d351315f0a \
    --periodo-horas 24

# Resultado: Score 0.42 (candidato #1), Q=-31,000 VAr
# Comparativa:
$ .venv/bin/python scripts/comparar_ti_bifasico.py \
    --device-a 7434647d-5b87-4d4e-b4a5-a0d351315f0a \
    --device-b c91713f1-0621-4a33-9279-c5327a317d96

# Resultado: Q signos opuestos pero configs iguales
# Interpretación: ¿Cargas realmente diferentes o TI invertido en A?
# Acción: Validar con patrón certificado o comparar con medidor de referencia conocido
```

### Caso C: Necesita corrección basada en ranking

```bash
$ .venv/bin/python scripts/diagnosticar_ti.py \
    --device-id abc123... \
    --periodo-horas 168

# Candidato #1: Score 0.55 (bajo)
# Candidato #2: Score 0.89 (bueno)
# Acción: Evaluar candidato #2 con patrón certificado
# Si es correcto:

$ .venv/bin/python scripts/generar_propuesta_ti.py \
    --device-id abc123... \
    --candidato-rango 2 \
    --output propuesta.json

# Aplicar propuesta
$ curl -X PATCH https://api.datamaq.com.ar/api/v1/dispositivos/abc123... \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d @propuesta.json

# Monitorear 24h: Q debe cambiar de signo
```

## Validación con Patrón Certificado

El patrón certificado es una **referencia metrológica independiente** (analizador trifásico, certificación de medidor, etc.).

**Procedimiento:**

1. Conectar patrón en paralelo al medidor (o tablero)
2. Anotar:
   - P, Q, S del medidor en cuestión
   - P, Q, S del patrón certificado
3. Comparar signos de Q:
   - Mismo signo: Config del medidor correcta
   - Signos opuestos: TI invertido (necesita corrección)

**Nota:** El patrón valida la polaridad; el diagnóstico por software valida el **orden de fases** (menos frecuente que inversión).

## Límites y Recomendaciones

| Condición | Recomendación |
|-----------|---------------|
| Score > 0.98 | Aceptar (validación completada) |
| 0.70 < Score ≤ 0.98 | Validar con patrón certificado |
| Score ≤ 0.70 | Revisar cableado + patrón certificado |
| Cargas dinámicas (compresor, motor variable) | Extender período a 7+ días |
| Cargas nocturnas/diurnas muy diferentes | Analizar períodos separados |
| Bifásico (R,S) o trifásico (R,S,T) | Auto-detectado por BD |

## Troubleshooting

### "Error: Dispositivo no encontrado"

Verificar UUID en `SELECT id, device_uid FROM devices WHERE id='...'`

### "No se encontraron registros"

Verif icar que el dispositivo tiene datos:
```sql
SELECT MAX(recorded_at), COUNT(*) FROM telemetry_instantaneous WHERE device_id='...'
```

### "Todos los candidatos tienen score bajo"

Posibles causas:
1. Medidor recién instalado (datos inconsistentes)
2. Problema de instalación (TI desconectado, cruzado, cascada)
3. Cargas muy variables (motor arranque/parada)

**Acción:** Ejecutar `scripts/diagnosticar_instalacion_ti.py` para detectar problemas de cableado.

### "Q no cambia de signo tras aplicar propuesta"

Posibles causas:
1. Propuesta no se aplicó (validar PATCH response)
2. BD no está sincronizada (cache o réplica)
3. Medidor no actualizó config (firmware obsoleto)

**Acción:** Esperar 5 min, refrescar BD, validar con `GET /api/v1/dispositivos/<id>`

## Performance

- Análisis de 24h (1440 registros): ~500ms
- Análisis de 7 días (10,080 registros): ~3s
- Comparativa de 2 medidores (10d × 2): ~6s

Sin restricciones en períodos > 30 días.

## Referencias

- [YAML de configuración de dispositivos](../data/organizaciones.yml)
- [Entidad Dispositivo](../src/domain/telemetria/entities.py#L220)
- [Script de auditoría de instalación](./diagnosticar_instalacion_ti.py)
- [Servicio de análisis de calidad](../src/domain/telemetria/services.py)
