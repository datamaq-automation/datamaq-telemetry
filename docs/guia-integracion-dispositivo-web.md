# Arquitectura y Guía de Integración End-to-End: Del Dispositivo Físico a la Aplicación Web

> **Documento:** `docs/guia-integracion-dispositivo-web.md`  
> **Destino:** Equipo de Desarrollo Web y Frontend (`app-datamaq`)  
> **Origen:** Equipo Backend & IoT (`datamaq-telemetry`)  
> **Estado:** Vigente  
> **Fecha:** 2026-08-22  

---

## 1. El Flujo Completo de la Información (De la Fábrica a la Pantalla)

El objetivo de este sistema es capturar en tiempo real las variables eléctricas de una planta industrial o comercio, procesarlas en nanosegundos en el servidor backend y presentarlas de manera fluida y comprensible en la aplicación web del usuario.

```
┌─────────────────────────┐
│  Dispositivo Físico     │  Medidor Powermeter (ESP32) instalado en tablero eléctrico.
│  (Tablero Eléctrico)    │  Mide transformadores de corriente (TI) y tomas de tensión.
└───────────┬─────────────┘
            │  📡 Protocolo MQTT (vía Wi-Fi o 4G)
            │  Publica cada 1 a 5 segundos en tópico: m/wifi/{MAC}/inst
            ▼
┌─────────────────────────┐
│  Broker MQTT            │  Servidor Mosquitto / EMQX.
│  (Receptor de Mensajes) │  Recibe y enruta los paquetes ligeros binarios/JSON.
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Backend Telemetry      │  datamaq-telemetry (FastAPI + Paho-MQTT Worker).
│  (Motor de Inteligencia)│  1. Deduplica paquetes repetidos.
│                         │  2. Calcula en vuelo: Desbalance VUR, Potencias, FP.
│                         │  3. Evalúa reglas de alerta (Subtensión, Sobretensión, VUR > 2%).
│                         │  4. Aplica filtro temporal anti-transitorios (3 segundos).
│                         │  5. Guarda histórico en Base de Datos (MySQL) con downsampling.
└───────────┬─────────────┘
            │
      ┌─────┴─────────────────────────┐
      │                               │
      │ ⚡ En Vivo (WebSocket / SSE)   │ 💾 Datos Históricos (REST API)
      │ Latencia < 500 ms             │ Consultas y Gráficos
      ▼                               ▼
┌───────────────────────────────────────────────────────────┐
│  Aplicación Web (app-datamaq)                             │
│  - Gauges y agujas simétricas en vivo (R, S, T, VUR).     │
│  - Gráficos históricos de tendencia y consumo (kWh).      │
│  - Panel de Alertas en tiempo real con severidades.       │
└───────────────────────────────────────────────────────────┘
```

---

## 2. Los Dos Canales de Datos para la Web: ¿En Vivo o Histórico?

La aplicación web consume dos tipos de flujos de datos según lo que necesita mostrar en pantalla:

### Canal A: Datos en Tiempo Real (*Live Stream*)
* **Para qué se usa:** Para los relojes velocímetros (Gauges), medidores de potencia instantánea, indicadores de corriente y badges de alerta en vivo en el Dashboard principal.
* **Mecanismo:** El backend retransmite inmediatamente cada paquete MQTT recibido hacia la web mediante WebSockets o Eventos de Servidor (SSE) sin pasar por esperas de base de datos.
* **Frecuencia:** Cada 1 a 5 segundos.

### Canal B: Datos Históricos y Analítica (*REST API*)
* **Para qué se usa:** Para graficar curvas temporales de las últimas 24 horas, calcular el consumo acumulado mensual (kWh) o revisar el historial de alertas pasadas.
* **Mecanismo:** Consultas HTTP estándar autenticadas vía Cookie `HttpOnly` (`datamaq_token`).
* **Frecuencia:** A demanda cuando el usuario entra a una pantalla o selecciona un rango de fechas.

---

## 3. Contratos de la API REST para Desarrolladores Web

La URL base de la API de telemetría es `/api/telemetria`. Todos los endpoints que reciben `{device_id}` aceptan de forma polimórfica tanto el UUID interno (ej. `7d32ab0f-...`) como la dirección MAC del equipo (ej. `001122334401` o `00:11:22:33:44:01`).

### 3.1 Obtener la Última Foto del Medidor (`GET /latest/{device_id}`)
Devuelve la lectura instantánea más reciente (con el desbalance ya calculado) y la energía acumulada.

* **Endpoint:** `GET /api/telemetria/latest/{device_id}`
* **Respuesta Exitosa (200 OK):**
```json
{
  "device_id": "7d32ab0f-bc81-4b4a-a401-a0600c105e7f",
  "instantanea": {
    "id": 10842,
    "dispositivo_id": "7d32ab0f-bc81-4b4a-a401-a0600c105e7f",
    "registrado_en": "2026-08-22T10:45:00Z",
    "fase_r": {
      "voltage_V": 226.5,
      "current_A": 8.4,
      "net_active_power_W": 1850.0,
      "power_factor": 0.97
    },
    "fase_s": {
      "voltage_V": 221.0,
      "current_A": 8.1,
      "net_active_power_W": 1740.0,
      "power_factor": 0.97
    },
    "fase_t": {
      "voltage_V": 218.0,
      "current_A": 8.3,
      "net_active_power_W": 1760.0,
      "power_factor": 0.97
    },
    "potencia_activa_total_W": 5350.0,
    "potencia_reactiva_total_VAR": 820.0,
    "potencia_aparente_total_VA": 5410.0,
    "factor_potencia_total": 0.97,
    "desbalance_tension_porcentaje": 2.11
  },
  "energia": {
    "id": 542,
    "dispositivo_id": "7d32ab0f-bc81-4b4a-a401-a0600c105e7f",
    "registrado_en": "2026-08-22T10:45:00Z",
    "net_active_energy_kwh": 14250.85,
    "imported_active_energy_kwh": 14250.85,
    "exported_active_energy_kwh": 0.0
  }
}
```

---

### 3.2 Listar Curvas Históricas para Gráficos (`GET /instantaneous/{device_id}`)
Devuelve un arreglo de lecturas para dibujar gráficos de series temporales (ej. Chart.js, Apache ECharts o ApexCharts).

* **Endpoint:** `GET /api/telemetria/instantaneous/{device_id}?limit=100&hours=24`
* **Parámetros Query:**
  * `limit` (opcional, entero, default: 100, max: 1000): Cantidad máxima de registros.
  * `hours` (opcional, entero): Filtrar solo las últimas N horas.
* **Respuesta (200 OK):**
```json
[
  {
    "id": 10842,
    "dispositivo_id": "7d32ab0f-bc81-4b4a-a401-a0600c105e7f",
    "registrado_en": "2026-08-22T10:45:00Z",
    "fase_r": { "voltage_V": 226.5, "current_A": 8.4, "net_active_power_W": 1850.0, "power_factor": 0.97 },
    "fase_s": { "voltage_V": 221.0, "current_A": 8.1, "net_active_power_W": 1740.0, "power_factor": 0.97 },
    "fase_t": { "voltage_V": 218.0, "current_A": 8.3, "net_active_power_W": 1760.0, "power_factor": 0.97 },
    "potencia_activa_total_W": 5350.0,
    "desbalance_tension_porcentaje": 2.11
  }
]
```

---

### 3.3 Consultar y Gestionar Alertas (`GET /api/alertas`)

* **Listar Alertas:** `GET /api/alertas?device_id={device_id}&solo_abiertas=true&limit=100`
* **Estructura de una Alerta:**
```json
{
  "id": 89,
  "dispositivo_id": "7d32ab0f-bc81-4b4a-a401-a0600c105e7f",
  "tipo_alerta": "DESBALANCE_TENSION",
  "severidad": "WARNING",
  "mensaje": "Desbalance de tensión superior al límite normativo del 2%: 2.11%",
  "esta_resuelta": false,
  "disparada_en": "2026-08-22T10:45:00Z",
  "resuelta_en": null
}
```
* **Resolver una Alerta:** `POST /api/alertas/{alerta_id}/resolver` (requiere rol de escritura)

---

## 4. Guía de Interfaz y Buenas Prácticas para el Frontend Web

### 4.1 Semáforo Visual del Desbalance de Tensión (VUR)
El desbalance de tensión es un indicador crítico de salud de motores trifásicos. En la SPA debe representarse con los siguientes umbrales visuales:

| Valor VUR | Estado | Color Tailwind / Hex | Mensaje al Usuario |
| :--- | :--- | :--- | :--- |
| $\text{VUR} \le 2.0\%$ | **Normal** | `emerald-500` (`#10B981`) | Red equilibrada bajo norma ENRE / IRAM 2001. |
| $2.0\% < \text{VUR} \le 3.0\%$ | **Advertencia** | `amber-500` (`#F59E0B`) | Supera límite normativo ($2\%$). Riesgo de sobrecalentamiento. |
| $\text{VUR} > 3.0\%$ | **Peligro Crítico** | `rose-600` (`#E11D48`) | Nivel destructivo NEMA ($>3\%$). Peligro de daño en motores. |

### 4.2 Indicador de Conexión del Medidor (Heartbeat)
* Cada dispositivo posee el campo `visto_por_ultima_vez` y `estado` (`ONLINE` / `OFFLINE`).
* Si el medidor no publica ningún mensaje durante más de **2 minutos**, el frontend debe mostrar una etiqueta visual de **"Desconectado / Sin señal"**.

### 4.3 Líneas Guía en los Gráficos de Tensión
En los gráficos históricos de tensión de las 3 fases ($V_R, V_S, V_T$), dibujar 4 líneas de referencia horizontales (Grid lines):
* **$248\text{ V}$ (Rojo punteado superior):** Sobretensión Crítica.
* **$242\text{ V}$ (Amarillo superior):** Límite Contractual ENRE $+10\%$.
* **$198\text{ V}$ (Amarillo inferior):** Límite Contractual ENRE $-10\%$.
* **$190\text{ V}$ (Rojo punteado inferior):** Subtensión Crítica.

---

## 5. Glosario Rápido para el Desarrollador Web

* **MQTT:** Protocolo ultra-ligero que usa el medidor para enviar datos con mínimo consumo de ancho de banda.
* **ESP32:** El microcontrolador dentro del medidor Powermeter que lee los sensores y se conecta al Wi-Fi.
* **VUR (*Voltage Unbalance Rate*):** Porcentaje matemático de asimetría entre las 3 fases eléctricas.
* **Downsampling:** Estrategia del servidor para guardar en base de datos 1 registro cada 5 minutos en lugar de saturar el disco guardando 1 registro por segundo.
* **Filtro de Persistencia:** Lógica del backend que espera 3 segundos antes de disparar una alarma de baja tensión para no asustar al usuario con falsas alarmas cuando arranca un motor grande.
