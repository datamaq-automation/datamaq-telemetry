# Guía Canónica de Integración Frontend: Datamaq Telemetry Platform

> **Documento:** `docs/frontend-integration-guide.md`  
> **Destino:** Equipo de Desarrollo Web y Frontend (`app-datamaq` — Vue 3 / Pinia / Tailwind)  
> **Origen:** Equipo Backend & IoT (`datamaq-telemetry`)  
> **Estado:** Vigente / Fuente Canónica de Verdad  
> **Última Actualización:** 2026-08-23

---

## 1. Principio Arquitectónico Rector: *Thin Client / Backend SSOT*

Por directiva de arquitectura del ecosistema DataMaq:

1. **La SPA (`app-datamaq`) es una capa de presentación pura:** no realiza cálculos de ingeniería de potencia, fórmulas trigonométricas de compensación, estimaciones tarifarias de multas ni auditorías normativas locales. Su función es renderizar con fidelidad los datos normalizados provistos por el backend.
2. **El Backend (`datamaq-telemetry`) es la Única Fuente de la Verdad (SSOT):** todo análisis electrotécnico, cálculo de compensación de reactiva ($Q_c$), algoritmos de desbalance ($\text{VUR}$ e $\text{IUR}$) y auditoría normativa de red se ejecutan en el backend.

---

## 2. Autenticación, Sesión y Control de Acceso

### 2.1 Mecanismo de Sesión por Cookie HttpOnly
* **Transporte Seguro:** La autenticación principal se basa en una cookie `HttpOnly` (`datamaq_token`) emitida por el backend en `/api/v1/auth/login` o `/api/v1/auth/guest`. La SPA **no almacena tokens en `localStorage` ni firma tokens**.
* **Configuración de Cookie:** `HttpOnly=True`, `Path=/`, `Max-Age=AUTH_TOKEN_EXPIRA_MINUTOS * 60` (por defecto 120 min / configurable), `SameSite=Strict` en producción (configurable a `SameSite=Lax` en desarrollo local para soporte cross-port `localhost:5173` ↔ `localhost:8000`).
* **Fallback:** El backend acepta alternativamente el header `Authorization: Bearer <token>` para clientes sin soporte de cookies.

### 2.2 Endpoints de Autenticación

| Endpoint | Método | Acceso | Descripción |
| :--- | :---: | :---: | :--- |
| `/api/v1/auth/login` | `POST` | Público | Autenticación con `{"usuario": "...", "contrasena": "..."}`. Emite cookie y JWT. |
| `/api/v1/auth/guest` | `POST` | Público | **Acceso Invitado Stateless:** Emite cookie y JWT con rol `invitado` sin consultar la base de datos (con rate limiting por IP). |
| `/api/v1/auth/logout` | `POST` | Público | Cierre de sesión. Borra la cookie `datamaq_token`. |
| `/api/v1/auth/me` | `GET` | Autenticado | Devuelve la identidad y rol activo `{"usuario": "...", "rol": "admin" \| "operador" \| "invitado"}`. |

### 2.3 Matriz de Permisos por Rol

| Módulo / Rutas | `invitado` (Demo) | `operador` | `admin` |
| :--- | :---: | :---: | :---: |
| Consultas de Telemetría (`/api/v1/telemetria/*`, `/ws/live`) | ✅ Lectura | ✅ Lectura | ✅ Lectura |
| Consulta de Dispositivos, Plantas, Organizaciones y Planes (`GET`) | ✅ Lectura | ✅ Lectura | ✅ Lectura |
| Alta y Edición de Dispositivos y Metrología (`POST`, `PUT`, `PATCH`) | ❌ 403 Forbidden | ✅ Escritura | ✅ Escritura |
| Gestión de Plantas, Organizaciones y Planes (`POST`) | ❌ 403 Forbidden | ✅ Escritura | ✅ Escritura |
| Consulta de Alertas (`GET /api/v1/alertas`) | ✅ Lectura | ✅ Lectura | ✅ Lectura |
| Resolución de Alertas (`PATCH /api/v1/alertas/{id}/resolver`) | ❌ 403 Forbidden | ✅ Escritura | ✅ Escritura |
| Modificación de Diagrama Unifilar y Layout (`PUT /api/v1/plantas/*`) | ❌ 403 Forbidden | ✅ Escritura | ✅ Escritura |
| Purga de Telemetría (`POST /api/v1/system/purge`) | ❌ 403 Forbidden | ❌ 403 Forbidden | ✅ Admin |

---

## 3. Canales de Telemetría: Tiempo Real (WS) vs. Histórico (REST)

```
┌─────────────────────────────────────────────────────────────┐
│                    Canales de Telemetría                    │
├──────────────────────────────┬──────────────────────────────┤
│    Canal A: Tiempo Real      │    Canal B: Histórico REST   │
│    (WebSocket /ws/live)      │    (/api/v1/telemetria/...)     │
├──────────────────────────────┼──────────────────────────────┤
│ • Gauges y velocímetros      │ • Gráficos de tendencias     │
│ • Potencia y FP instantáneo  │ • Curvas de carga (24h, 7d)  │
│ • Latencia < 500 ms          │ • Auditoría de energía (kWh) │
│ • Push continuo del broker   │ • Consultas con downsampling │
└──────────────────────────────┴──────────────────────────────┘
```

### 3.1 Canal en Tiempo Real (`WS /ws/live`)
* **Handshake Autenticado:** Requiere cookie `datamaq_token` o header `Authorization: Bearer`.
* **Alcance Global del Stream:** El stream WebSocket `/ws/live` es global para cualquier usuario autenticado, retransmitiendo en vivo los eventos MQTT (`m/wifi/{mac}/inst`, `m/wifi/{mac}/acc`, `m/wifi/{mac}/alertas`) sin filtrado por organización en esta iteración.
* **Formato del Mensaje:**
```json
{
  "topic": "m/wifi/D48C49F03564/inst",
  "data": {
    "t": 1787447872,
    "f": [
      {"n": "R", "v": 224.5, "i": 150.2, "p": 33200, "q": 22500},
      {"n": "S", "v": 220.1, "i": 153.0, "p": 33100, "q": 22400},
      {"n": "T", "v": 222.8, "i": 148.5, "p": 33300, "q": 22600}
    ]
  },
  "received_at": "2026-08-23T19:40:00.123456Z"
}
```

---

## 4. Analítica de Calidad de Energía y Compensación de Reactiva

El backend expone en cada lectura el bloque precalculado [`AnaliticaCalidadEnergiaDTO`](file:///home/agustin/proyectos_software/datamaq-telemetry/src/application/dtos/telemetria_dto.py#L18-L27).

### 4.1 Contratos TypeScript para la SPA

```typescript
export type EstadoFactorPotencia = 'OPTIMO' | 'ADVERTENCIA' | 'PENALIZADO';
export type EstadoTension = 'NORMAL' | 'SUBTENSION' | 'SOBRETENSION';

export interface AnaliticaCalidadEnergiaDTO {
  // Compensación de Reactiva
  requiere_compensacion: boolean;
  potencia_reactiva_a_compensar_kvar: number | null; // Qc calculado (kVAr)
  banco_sugerido_kvar: number | null; // Escalón comercial normalizado estándar (kVAr)
  penalizacion_estimada_ars: number | null; // Recargo mensual estimado en factura ($ ARS)
  recargo_porcentaje: number | null; // % de recargo sobre el cargo de potencia por FP < 0.95

  // Alcance tarifario (D-11, 2026-09-13): cuándo el backend se abstiene de emitir
  // veredicto de reactiva porque la categoría del dispositivo no está alcanzada
  // por el régimen (Programa de Mejora del FP, ENRE). "TARIFA_SIN_CARGO_REACTIVA"
  // es el único valor emitido hoy; en ese caso requiere_compensacion es false y
  // penalizacion_estimada_ars es null. No inferir la exención de fases_con_ti —
  // depende únicamente de categoria_tarifaria/penalizacion_reactiva_aplica del
  // dispositivo (ver §6), que el backend ya resuelve.
  motivo_abstencion: string | null;

  // Ventana de evaluación (D-12, pendiente: hoy siempre 15 e instantáneo salvo
  // que el backend ya haya migrado a ventana integrada)
  ventana_evaluacion_min: number | null;
  vigente_desde: string | null; // ISO 8601 UTC, desde cuándo se sostiene el veredicto
  factor_potencia_integrado: number | null; // FP promedio de la ventana, si aplica

  // Desbalances Normativos (IEC 61000-4-30 / NEMA)
  desbalance_tension_porcentaje: number | null; // VUR %
  desbalance_corriente_porcentaje: number | null; // IUR %

  // Estados Normativos
  estado_fp: EstadoFactorPotencia;
  estado_tension: EstadoTension;
}

export interface MedicionFaseDTO {
  voltage_V: number | null;
  current_A: number | null;
  net_active_power_W: number | null;
  net_reactive_power_VAR: number | null;
  net_apparent_power_VA: number | null;
  power_factor: number | null;
  thd_v_pct?: number | null;
  thd_i_pct?: number | null;
}

export interface LecturaInstantaneaDTO {
  id?: number | null;
  dispositivo_id: string;
  registrado_en: string; // ISO 8601 UTC
  fase_r: MedicionFaseDTO;
  fase_s: MedicionFaseDTO;
  fase_t: MedicionFaseDTO;
  potencia_activa_total_W: number | null;
  potencia_reactiva_total_VAR: number | null;
  potencia_aparente_total_VA: number | null;
  factor_potencia_total: number | null;
  desbalance_tension_porcentaje: number | null;
  corriente_neutro_estimada_A: number | null;
  voltage_linea_V: number | null;
  tension_neutro_estimada_V: number | null;
  thd_v_promedio_pct: number | null;
  thd_i_total_pct: number | null;
  analitica?: AnaliticaCalidadEnergiaDTO | null;
}

export interface TelemetriaLatestResponseDTO {
  device_id: string;
  instantanea: LecturaInstantaneaDTO | null;
  energia: AcumuladoEnergiaDTO | null;
  analitica?: AnaliticaCalidadEnergiaDTO | null;
}
```

### 4.2 Endpoint `GET /api/v1/telemetria/latest/{device_id}`
* `{device_id}` acepta polimórficamente UUID (`725dfb4c-...`) o dirección MAC (`D48C49F03564` / `d4:8c:49:f0:35:64`).
* **Ejemplo de Respuesta JSON:**
```json
{
  "device_id": "725dfb4c-2610-4405-878a-d718b4f428a4",
  "instantanea": {
    "potencia_activa_total_W": 99600.0,
    "factor_potencia_total": 0.82,
    "desbalance_tension_porcentaje": 0.45,
    "corriente_neutro_estimada_A": 3.12,
    "voltage_linea_V": 382.04,
    "tension_neutro_estimada_V": 1.25,
    "analitica": {
      "requiere_compensacion": true,
      "potencia_reactiva_a_compensar_kvar": 40.48,
      "banco_sugerido_kvar": 50.0,
      "penalizacion_estimada_ars": 1098487.80,
      "desbalance_tension_porcentaje": 0.45,
      "desbalance_corriente_porcentaje": 1.48,
      "estado_fp": "PENALIZADO",
      "estado_tension": "NORMAL"
    }
  },
  "energia": {
    "net_active_energy_kwh": 48293.12,
    "net_reactive_energy_kvarh": 32104.55
  },
  "analitica": {
    "requiere_compensacion": true,
    "potencia_reactiva_a_compensar_kvar": 40.48,
    "banco_sugerido_kvar": 50.0,
    "penalizacion_estimada_ars": 1098487.80,
    "desbalance_tension_porcentaje": 0.45,
    "desbalance_corriente_porcentaje": 1.48,
    "estado_fp": "PENALIZADO",
    "estado_tension": "NORMAL"
  }
}
```

### 4.3 Endpoint Histórico `GET /api/v1/telemetria/instantaneous/{device_id}`
* **Query Parameters:**
  * `limit`: Entero (1 a 5000, default `500`).
  * `hours`: Entero (1 a 720, ej: `2`, `24`, `168`).
  * `granularity`: Remuestreo inteligente (`auto`, `raw`, `1m`, `5m`, `15m`, `1h`).

---

## 5. Gestión de Incidentes y Alertas Normativas

### 5.1 Listar Alertas
* **Endpoint:** `GET /api/v1/alertas?device_id={id}&solo_abiertas={bool}&severidad={WARNING|CRITICAL}&limit=100`

### 5.2 Resolver Alerta
* **Endpoint:** `PATCH /api/v1/alertas/{alerta_id}/resolver` (o `POST`)
* **Body Opcional:**
```json
{
  "observaciones": "Se procedió a balancear cargas en la fase S del TGBT."
}
```

### 5.3 Tipos de Alertas de Red
* `BAJA_TENSION` ($V < 198\text{V}$) y `SOBRETENSION` ($V > 242\text{V}$).
* `DESBALANCE_TENSION` ($\text{VUR} > 2.0\%$).
* `BAJO_FACTOR_POTENCIA` ($\text{FP} < 0.95$).
* `TI_INVERTIDO` (Detección de potencia negativa con corriente activa).
* `ALTO_THD_TENSION_WARNING` ($>5\%$) y `ALTO_THD_TENSION_CRITICAL` ($>8\%$).
* `ALTO_THD_CORRIENTE` ($>20\%$).
* `RIESGO_RESONANCIA_CAPACITORES`.

---

## 6. Configuración de Metrología y Dispositivos (2-TI)

Para editar parámetros de instalación de un medidor en campo:

* **Endpoint:** `PATCH /api/v1/dispositivos/{device_id}` (o `PUT`)
* **Payload:**
```json
{
  "nombre": "Tablero General TGBT Nave 1",
  "ubicacion_tag": "Sala de Transformadores",
  "numero_serie": "377",
  "tipo_instalacion": "3P4W",
  "fases_con_ti": "R,S,T",
  "planta_id": "8f5a1e2b-...",
  "categoria_tarifaria": "T1-R",
  "penalizacion_reactiva_aplica": false
}
```
* **Opciones de `fases_con_ti`:** `"R,S,T"` (Trifásico 4 hilos), `"S,T"` o `"R,T"` (Método Aron / 2-TI).
* **`categoria_tarifaria`** (`T1-R | T1-G | T2 | T3`, default `"T2"`) y **`penalizacion_reactiva_aplica`**
  (`boolean`, default `true`) — desde 2026-09-13 son columnas reales persistidas (antes de esa
  fecha existían en el contrato pero el `PATCH` era un no-op silencioso: nunca se guardaban).
  Determinan `analitica.motivo_abstencion` en el bloque de §4 — `"T1-R"` o `"RESIDENCIAL"` en la
  categoría, o `penalizacion_reactiva_aplica: false` explícito, hacen que el backend se abstenga
  del veredicto de reactiva (`"TARIFA_SIN_CARGO_REACTIVA"`). **No es automático por ser
  monofásico:** un `"T1-G"` (comercio, consorcio) monofásico con medición de reactiva sigue
  alcanzado por el cargo — hay que declarar la categoría real, no inferirla de `fases_con_ti`.

---

## 7. Diagrama Unifilar y Layout 2D de Planta

Endpoints para persistencia y renderizado dinámico de la infraestructura de planta:

* `GET /api/v1/planta/unifilar?planta_id=...`: Árbol jerárquico de tableros y medidores.
* `PUT /api/v1/plantas/{planta_id}/unifilar`: Guardar topología unifilar.
* `GET /api/v1/planta/layout?planta_id=...`: Zonas de planta y ubicación porcentual (`pos_x_pct`, `pos_y_pct`) de los tableros sobre el plano SVG.
* `PUT /api/v1/plantas/{planta_id}/layout`: Guardar distribución espacial 2D.

---

## 8. Módulo de Disponibilidad y Segmentación Modal de Potencia

### 8.1 Histograma de Potencia y Partición Modal

Permite a la SPA visualizar la distribución histórica de potencia de una máquina, sus regímenes de operación identificados algorítmicamente (standby, marcha baja, marcha plena) y el umbral sugerido marcha/parada.

* **Endpoint:** `GET /api/v1/disponibilidad/maquinas/{maquina_id}/histograma?dias={1..90}`
* **Query Params:** `dias` (opcional, por defecto `7`, rango 1 a 90).

> [!WARNING]
> **Contrato de Bins de Ancho Variable (Escala Logarítmica en Potencia):**
> * El array `bordes_bins_w` contiene exactamente $n+1$ bordes para $n$ elementos en `frecuencias`.
> * Debido al binning en escala logarítmica, **los bins tienen ancho variable en Watts** (angostos en baja potencia para resolver standby, anchos en alta potencia para marcha).
> * La SPA **no debe asumir espaciado uniforme** en el eje X (no asumir `ancho = bordes[1] - bordes[0]`). Cada barra $i$ se extiende desde `bordes_bins_w[i]` hasta `bordes_bins_w[i+1]`.

#### Payload de Respuesta (`HistogramaPotenciaResponseDTO`):
```json
{
  "dispositivo_id": "dev-cnc-01",
  "dias_analizados": 7,
  "cantidad_lecturas": 2016,
  "bordes_bins_w": [18.5, 22.1, 26.4, "...", 3250.0],
  "frecuencias": [45, 120, 310, "...", 12],
  "umbral_sugerido_w": 145.5,
  "escala": "logaritmica",
  "epsilon_w": 0.05,
  "lecturas_truncadas": false,
  "lecturas_descartadas": 2,
  "regimenes": [
    {
      "indice": 0,
      "potencia_tipica_w": 28.5,
      "limite_inferior_w": 18.5,
      "limite_superior_w": 145.5,
      "masa": 0.625,
      "mediana_w": 28.2,
      "mad_w": 3.1,
      "persistencia": 1.0,
      "variacion_mediana_w_s": 0.012,
      "naturaleza": "ESTABLE"
    },
    {
      "indice": 1,
      "potencia_tipica_w": 2150.0,
      "limite_inferior_w": 145.5,
      "limite_superior_w": 3250.0,
      "masa": 0.375,
      "mediana_w": 2140.0,
      "mad_w": 65.4,
      "persistencia": 0.85,
      "variacion_mediana_w_s": 0.045,
      "naturaleza": "ESTABLE"
    }
  ],
  "diagnostico_modal": {
    "num_modas_estable": 2,
    "fraccion_ventanas_consistentes": 0.875,
    "es_multimodal_confiable": true
  },
  "diagnostico_estacionariedad": {
    "num_subventanas": 4,
    "desplazamiento_maximo_w": 15.2,
    "desplazamiento_maximo_relativo": 0.007,
    "es_estacionario": true
  }
}
```

* **`naturaleza` de un régimen:**
  * `"ESTABLE"`: La tasa $|\Delta P|/\Delta t$ es baja comparada con el ancho de banda del régimen (la máquina permanece operando allí).
  * `"TRANSITORIO"`: Tasa alta de variación (la máquina cruza rápidamente esa banda).
  * `"INDETERMINADO"`: Cadencia insuficiente (ej. 5 minutos estándar) o falta de lecturas temporales para sostener la clasificación con respaldo metrológico.

### 8.2 Gestión de Máquinas y Disponibilidad

* `GET /api/v1/disponibilidad/maquinas`: Listar máquinas registradas con su estado de calibración y umbrales.
* `POST /api/v1/disponibilidad/maquinas`: Registrar máquina vinculada a un `dispositivo_id`.
* `PATCH /api/v1/disponibilidad/maquinas/{id}`: Actualizar nombre, umbral manual (`umbral_marcha_w`), o ventana de persistencia anti-transitorios (`ventana_persistencia_lecturas`, `ventana_persistencia_segundos`).
* `GET /api/v1/disponibilidad/maquinas/{id}/eventos?limite=100`: Listar eventos históricos de marcha/parada.
* `POST /api/v1/disponibilidad/eventos/{id}/corregir`: Corrección humana de estado (`{"tipo_parada": "PROGRAMADA", "comentario": "..."}`).
* `POST /api/v1/disponibilidad/paradas-programadas`: Carga de paradas programadas de mantenimiento (`{"maquina_id": "...", "inicio_at": "...", "fin_at": "...", "motivo": "..."}`).

