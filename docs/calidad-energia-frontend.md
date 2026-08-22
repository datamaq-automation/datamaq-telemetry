# Guía de Integración Frontend: Calidad de Energía, Desbalance Trifásico y Alertas Normativas

> **Documento:** `docs/calidad-energia-frontend.md`  
> **Destino:** `app-datamaq` (Frontend SPA - Vue 3 / Pinia / Tailwind)  
> **Origen:** `datamaq-telemetry` (Backend FastAPI + MQTT Ingestion)  
> **Estado:** Vigente  
> **Fecha:** 2026-08-22  

---

## 1. Resumen de Capacidades del Backend

El backend `datamaq-telemetry` implementa de forma nativa el cálculo, persistencia y monitoreo normativo de calidad de suministro eléctrico para redes trifásicas de Baja Tensión ($220\text{ V} / 380\text{ V}, 50\text{ Hz}$):

1. **Cálculo de Desbalance de Tensión Trifásico (VUR — NEMA/IEC):**
   $$V_{prom} = \frac{V_R + V_S + V_T}{3}$$
   $$\text{VUR (\%)} = \frac{\max(|V_R - V_{prom}|, |V_S - V_{prom}|, |V_T - V_{prom}|)}{V_{prom}} \times 100$$
2. **Esquema de Alertas de Tensión de Dos Niveles (Norma ENRE vs. Peligro Crítico).**
3. **Filtro de Persistencia Temporal:** Supresión automática de falsos positivos por transitorios de arranque de motores ($< 2$ lecturas consecutivas o $< 3\text{ s}$).

---

## 2. Cambios en DTOs y Endpoints REST

### 2.1 Campo `desbalance_tension_porcentaje` en `LecturaInstantaneaDTO`

Todas las respuestas que incluyen lecturas instantáneas incorporan ahora la propiedad opcional `desbalance_tension_porcentaje` (`number | null`):

```typescript
export interface MedicionFaseDTO {
  voltage_V: number | null;
  current_A: number | null;
  net_active_power_W: number | null;
  net_reactive_power_VAR: number | null;
  net_apparent_power_VA: number | null;
  power_factor: number | null;
}

export interface LecturaInstantaneaDTO {
  id: number | null;
  dispositivo_id: string;
  registrado_en: string; // ISO 8601 UTC
  fase_r: MedicionFaseDTO;
  fase_s: MedicionFaseDTO;
  fase_t: MedicionFaseDTO;
  potencia_activa_total_W: number | null;
  potencia_reactiva_total_VAR: number | null;
  potencia_aparente_total_VA: number | null;
  factor_potencia_total: number | null;
  desbalance_tension_porcentaje: number | null; // NUEVO: % VUR redondeado a 2 decimales
}
```

### 2.2 Endpoints Afectados

1. **`GET /api/v1/telemetria/dispositivos/{id_o_uid}/latest`**
   ```json
   {
     "device_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
     "instantanea": {
       "id": 1042,
       "dispositivo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
       "registrado_en": "2026-08-22T10:30:00Z",
       "fase_r": { "voltage_V": 228.5, "current_A": 4.2, "net_active_power_W": 950.0, "net_reactive_power_VAR": 120.0, "net_apparent_power_VA": 960.0, "power_factor": 0.98 },
       "fase_s": { "voltage_V": 221.0, "current_A": 3.8, "net_active_power_W": 830.0, "net_reactive_power_VAR": 110.0, "net_apparent_power_VA": 840.0, "power_factor": 0.98 },
       "fase_t": { "voltage_V": 216.5, "current_A": 4.0, "net_active_power_W": 860.0, "net_reactive_power_VAR": 115.0, "net_apparent_power_VA": 870.0, "power_factor": 0.98 },
       "potencia_activa_total_W": 2640.0,
       "potencia_reactiva_total_VAR": 345.0,
       "potencia_aparente_total_VA": 2670.0,
       "factor_potencia_total": 0.98,
       "desbalance_tension_porcentaje": 2.93
     },
     "energia": { ... }
   }
   ```

2. **`GET /api/v1/telemetria/dispositivos/{id_o_uid}/instantaneas?limite=100`**
   * Retorna una lista `LecturaInstantaneaDTO[]` ordenada descendentemente por `registrado_en`, apta para graficar series temporales de desbalance.

---

## 3. Esquema de Alertas de Calidad de Energía

Las alertas se consultan vía `GET /api/v1/alertas` (con filtros `dispositivo_id` y `solo_abiertas=true|false`).

### 3.1 Tipos de Alerta y Severidades

| `tipo_alerta` | Condición Eléctrica | `severidad` | Mensaje de Ejemplo |
| :--- | :--- | :--- | :--- |
| `DESBALANCE_TENSION` | $2.0\% < \text{VUR} \le 3.0\%$ | `WARNING` | `"Desbalance de tensión superior al límite normativo del 2%: 2.73%"` |
| `DESBALANCE_TENSION` | $\text{VUR} > 3.0\%$ | `CRITICAL` | `"Desbalance de tensión superior al límite normativo del 2%: 4.85%"` |
| `BAJA_TENSION` | $190.0\text{ V} \le V < 198.0\text{ V}$ | `WARNING` | `"Baja tensión detectada en Fase R: 194.5V (Mínimo: 198.0V)"` |
| `BAJA_TENSION` | $V < 190.0\text{ V}$ | `CRITICAL` | `"Baja tensión detectada en Fase R: 184.0V (Mínimo: 190.0V)"` |
| `SOBRETENSION` | $242.0\text{ V} < V \le 248.0\text{ V}$ | `WARNING` | `"Sobretensión detectada en Fase T: 245.2V (Máximo: 242.0V)"` |
| `SOBRETENSION` | $V > 248.0\text{ V}$ | `CRITICAL` | `"Sobretensión detectada en Fase T: 252.0V (Máximo: 248.0V)"` |

---

## 4. Guía de Implementación en la SPA (`app-datamaq`)

### 4.1 Visualización de Medidores Simétricos y Desbalance (Gauge / Badges)
* **Condición Normal ($\text{VUR} \le 2.0\%$):** Badge verde / neutro (ej. `bg-emerald-100 text-emerald-800`).
* **Advertencia Normativa ($2.0\% < \text{VUR} \le 3.0\%$):** Badge amarillo/naranja con advertencia por superación de límite IRAM/ENRE ($2\%$).
* **Peligro Crítico ($\text{VUR} > 3.0\%$):** Badge rojo parpadeante con advertencia de riesgo de sobrecalentamiento en motores trifásicos.

### 4.2 Panel de Alertas (`AlertsPanel.vue`)
* Mapear `tipo_alerta === 'DESBALANCE_TENSION'` con ícono de advertencia trifásica (ej. `heroicons/exclamation-triangle` o `bolt-slash`).
* Soporte para resolver alertas mediante `POST /api/v1/alertas/{id}/resolver`.

### 4.3 Gráficos Históricos de Tendencia
* En las vistas de telemetría histórica, se puede proyectar una curva para `desbalance_tension_porcentaje` con dos líneas de referencia horizontales:
  * Línea de advertencia en $2.0\%$ (umbral normativo ENRE / IRAM).
  * Línea crítica en $3.0\%$ (umbral destructivo de motores NEMA MG1).
