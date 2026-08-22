# Mejora Backend: Estimación de Tensión de Neutro

## Contexto

El backend ahora calcula y persiste la **tensión de neutro estimada** (`tension_neutro_estimada`) para cada lectura instantánea de telemetría. Esta métrica complementa la ya existente `corriente_neutro_estimada_A` y permite al frontend mostrar un indicador adicional de calidad de energía.

## Cambios Realizados

### 1. Nuevo campo en el dominio

Se añadió el atributo `tension_neutro_estimada` a la entidad `LecturaInstantanea` en `src/domain/telemetria/entities.py`. Este campo es opcional (`float | None`) y se calcula mediante el servicio `AnalizadorCalidadEnergiaService.calcular_tension_neutro()`.

### 2. Cálculo en el caso de uso

En `src/application/use_cases/ingestar_telemetria.py`, dentro del flujo de procesamiento de lecturas instantáneas (`subtopico == "inst"`), se invoca:

```python
v_neutro = AnalizadorCalidadEnergiaService.calcular_tension_neutro(
    vr, vs, vt, ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
)
```

Este valor se asigna a la entidad `LecturaInstantanea` antes de su persistencia.

### 3. Persistencia en base de datos

El modelo SQLAlchemy `TelemetryInstantaneousModel` en `src/infrastructure/sqlalchemy/models.py` ahora incluye la columna `tension_neutro_estimada` de tipo `NUMERIC(6, 2)` (nullable). La migración correspondiente debe ejecutarse para actualizar el esquema.

### 4. Exposición en la API

El DTO `LecturaInstantaneaDTO` en `src/application/dtos/telemetria_dto.py` incluye el campo `tension_neutro_estimada_V: float | None = None`. El mapper `TelemetriaMapper.instantanea_to_dto()` lo rellena a partir de la entidad.

## Formato del campo en la respuesta JSON

El campo se expone con el nombre **`tension_neutro_estimada_V`** (con sufijo `_V` para indicar unidades). Ejemplo de respuesta:

```json
{
  "id": 123,
  "dispositivo_id": "abc-123",
  "registrado_en": "2026-08-22T10:30:00Z",
  "fase_r": { ... },
  "fase_s": { ... },
  "fase_t": { ... },
  "potencia_activa_total_W": 2500.0,
  "potencia_reactiva_total_VAR": 120.0,
  "potencia_aparente_total_VA": 2503.0,
  "factor_potencia_total": 0.99,
  "desbalance_tension_porcentaje": 1.2,
  "corriente_neutro_estimada_A": 0.05,
  "voltage_linea_V": 398.4,
  "tension_neutro_estimada_V": 0.8
}
```

## Interpretación para el frontend

- **Valor cercano a 0 V**: indica un sistema trifásico balanceado y sin problemas de neutro.
- **Valores elevados** (típicamente > 5 V en sistemas de 230 V fase‑neutro) pueden indicar:
  - Desbalance de cargas entre fases.
  - Presencia de armónicos de tercer orden.
  - Problemas de conexión a tierra.
- **Valor `null`**: no se pudo calcular (por ejemplo, faltan datos de alguna fase).

## Recomendaciones de visualización

- Mostrar el valor con 2 decimales y la unidad "V".
- Usar un indicador de color (verde/amarillo/rojo) según umbrales configurables (sugeridos: < 2 V verde, 2–5 V amarillo, > 5 V rojo).
- Incluir tooltip explicativo: "Tensión de neutro estimada a partir de las mediciones de fase".

## Notas técnicas

- El cálculo se basa en el método de componentes simétricas simplificado, asumiendo sistema trifásico de 4 hilos.
- La precisión depende de la calidad de las mediciones de tensión y corriente de cada fase.
- Este campo es **estimado**, no medido directamente por el dispositivo.
````
