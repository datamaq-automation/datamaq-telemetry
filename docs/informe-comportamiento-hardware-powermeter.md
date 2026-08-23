# Informe Técnico: Hallazgos Empíricos del Comportamiento del Hardware Powermeter

**Fecha:** 22 de Agosto de 2026  
**Ambiente de Inspección:** VPS Producción (`datamaq-telemetry` / Mosquitto MQTT Broker)  
**Dispositivo Analizado:** Powermeter SmartPlus (`D48C49F03564`, Serie 377)  
**Estado:** Confirmado mediante captura de tráfico y verificación de persistencia en base de datos.

---

## 1. Resumen Ejecutivo

Durante las pruebas de validación con hardware real conectado al broker MQTT de producción, se procedió a inspeccionar y contrastar la especificación teórica preliminar con el comportamiento empírico del firmware de los medidores de energía **Powermeter SmartPlus**.

Los hallazgos confirman que el hardware implementa un esquema de **muestreo y publicación periódico cada 5 minutos (300 segundos)** en lugar de transmisión continua en tiempo real (1-5 segundos), con una sincronización basada en reloj de red (segundo `:01` de cada ventana) y un formato de payload JSON compacto mediante arreglos por fase.

Este patrón de operación reduce significativamente la carga de I/O sobre el motor de base de datos, garantizando una alta estabilidad y bajo consumo de ancho de banda y almacenamiento.

---

## 2. Perfil e Identificación del Dispositivo

Metadatos extraídos de la trama de diagnóstico `status` emitida por el equipo:

| Parámetro | Valor Observado | Descripción |
|---|---|---|
| **Modelo de Equipo** | `SmartPlus` | Familia de medidores trifásicos / monofásicos inteligentes |
| **Modelo de Hardware** | `HOME V2.0` | Versión de placa base física |
| **Microcontrolador** | `ESP32` (Core FW: `V2.0.5`) | CPU y stack de conectividad Wi-Fi/IP |
| **Versión de Firmware** | `V1.3.0` | Versión de aplicación del medidor |
| **MAC Address / UID** | `D4:8C:49:F0:35:64` / `D48C49F03564` | Identificador único y Client ID MQTT |
| **Número de Serie** | `377` | Identificador serial de fábrica |
| **Servidor Modbus TCP** | Activo (Puerto `502`) | Servidor esclavo Modbus local integrado |

---

## 3. Ciclo de Vida y Secuencia de Conexión

Al energizar el equipo o restablecer el enlace Wi-Fi/MQTT, el medidor emite una ráfaga inmediata de 3 mensajes de ciclo de vida y diagnóstico antes de comenzar la medición periódica:

```
[Arranque / Reconexión]
       │
       ├──► m/wifi/{UID}/onoff    (Versión microcódigo, hora de inicio y último apagado)
       ├──► m/wifi/{UID}/add      (Anuncio del equipo, email de contacto y nombre)
       └──► m/wifi/{UID}/status   (Diagnóstico Wi-Fi, RSSI, IP, uptime y salud del broker)
```

### Payloads Crudos de Ciclo de Vida Capturados:

#### `m/wifi/D48C49F03564/onoff`
```json
{
  "uc_mod": "Powermeter SmartPlus",
  "uc_ver": "V1.3.0",
  "uc_start": 1787447642,
  "uc_last_off": 1787272799
}
```

#### `m/wifi/D48C49F03564/add`
```json
{
  "dev_id": "D48C49F03564",
  "email": "agustin@datamaq.com.ar",
  "dev_name": "test"
}
```

#### `m/wifi/D48C49F03564/status`
```json
{
  "wifi_sta": {
    "enabled": true,
    "connected": true,
    "quality": 77,
    "dbm": -54,
    "ssid": "Telecentro-1397",
    "bssid": "20:b8:2b:2d:13:9c",
    "ip": "192.168.0.4",
    "gateway": "192.168.0.1",
    "subnet_mask": "255.255.255.0",
    "dns_1": "100.72.3.97",
    "dns_2": "100.72.3.117",
    "mac": "D4:8C:49:F0:35:64"
  },
  "mqtt": {
    "enabled": true,
    "connected": true,
    "connection": "wifi",
    "client_id": "D48C49F03564",
    "broker_host": "mqtt.datamaq.com.ar",
    "broker_port": 8883
  },
  "device_info": {
    "serial_number": "377",
    "user_email": "agustin@datamaq.com.ar",
    "device_name": "test",
    "device_contact": "",
    "device_location": "",
    "device_model": "SmartPlus",
    "device_fw": "V1.3.0",
    "core_model": "ESP32",
    "core_fw": "V2.0.5",
    "hw_model": "HOME V2.0",
    "hw_fw": "V1.3.0",
    "power_on_timestamp": 1787447642,
    "power_off_timestamp": 1787272799,
    "uptime": 341
  },
  "modbus_server": {
    "tcp_server_enabled": true,
    "tcp_server_port": 502,
    "map": "Powermeter",
    "active": false
  }
}
```

---

## 4. Cadencia de Muestreo y Tráfico de Telemetría

### Comportamiento Temporal Observado
1. **Frecuencia Nominal:** **Cada 5 minutos (300 segundos)**.
2. **Alineación de Reloj:** El hardware programa su envío en los segundos `:00` / `:01` de cada ventana fija de 5 minutos (ej: `00:05:01`, `00:10:01`, `00:15:01`, `00:20:01`, etc.).
3. **Ráfaga Coordinada:** En cada intervalo de 5 minutos, el medidor publica concurrentemente en 3 tópicos:
   * `m/wifi/{UID}/inst` (variables instantáneas)
   * `m/wifi/{UID}/acc` (acumulados por fase)
   * `m/wifi/{UID}/energyio` (balance de energía global)

### Payloads Crudos de Telemetría Capturados:

#### `m/wifi/D48C49F03564/inst` (Telemetría Instantánea)
```json
{
  "t": 1787447872,
  "a": 0,
  "f": [
    {"n": "R", "v": 225.0, "i": 0.0, "p": 0, "q": 0},
    {"n": "S", "v": 224.9, "i": 0.0, "p": -0, "q": 0},
    {"n": "T", "v": 225.4, "i": 0.0, "p": -0, "q": 0}
  ]
}
```
* `t`: Marca de tiempo Unix del medidor.
* `a`: Código / bandera de alarma local interna.
* `f`: Arreglo de mediciones por fase:
  * `n`: Nombre de fase (`"R"`, `"S"`, `"T"`).
  * `v`: Tensión eficaz (Voltios RMS).
  * `i`: Corriente eficaz (Amperios RMS).
  * `p`: Potencia activa neta (Vatios, con signo).
  * `q`: Potencia reactiva neta (VAR, con signo).

#### `m/wifi/D48C49F03564/acc` (Energía Acumulada por Fase)
```json
{
  "t": 1787447872,
  "a": 0,
  "f": [
    {"n": "R", "a": 0.03, "r": 0.01},
    {"n": "S", "a": 0.02, "r": 0.00},
    {"n": "T", "a": 0.03, "r": 0.01}
  ]
}
```
* `a`: Energía activa acumulada en la fase (kWh).
* `r`: Energía reactiva acumulada en la fase (kVARh).

#### `m/wifi/D48C49F03564/energyio` (Energía Global Bidireccional)
```json
{
  "t": 490696800,
  "ae_imp": 0.11,
  "ae_exp": 0.01,
  "re_imp": 0.05,
  "re_exp": 0.01
}
```
* `ae_imp`: Energía activa importada total (kWh).
* `ae_exp`: Energía activa exportada / generación (kWh).
* `re_imp`: Energía reactiva importada total (kVARh).
* `re_exp`: Energía reactiva exportada total (kVARh).

---

## 5. Análisis de Capacidad e Impacto en Base de Datos

Con una flota proyectada de **20 dispositivos** y la cadencia confirmada de **5 minutos**:

### 1. Métricas de Carga de Ingesta

$$\text{Tasa de Inserción} = \frac{20 \text{ dispositivos} \times 12 \text{ envíos/hora}}{3600 \text{ segundos}} \approx 0.067 \text{ req/s}$$

* **Por hora:** $20 \times 12 = \mathbf{240\text{ registros/hora}}$
* **Por día:** $240 \times 24 = \mathbf{5.760\text{ registros/día}}$
* **Por mes (30 días):** $5.760 \times 30 = \mathbf{172.800\text{ registros/mes}}$
* **Por año:** $\mathbf{\approx 2.073.600\text{ registros/año}}$

### 2. Dimensionamiento de Almacenamiento (InnoDB)
* Tamaño estimado por registro de telemetría (fila + índices B-Tree): $\approx 120\text{ bytes}$.
* Crecimiento mensual en disco: $\approx 20\text{ MB/mes}$.
* Crecimiento anual en disco: $\mathbf{\approx 250 - 300\text{ MB/año}}$.

### 3. Conclusión de Arquitectura de Datos
* **Buffer Pool / Memoria RAM:** El conjunto completo de datos activos del año cabe holgadamente en la memoria RAM del servidor VPS.
* **Índices:** El índice compuesto `(device_id, recorded_at)` en B-Tree resuelve consultas de rangos de días o meses de forma casi instantánea.
* **Particionamiento:** No es necesario particionar las tablas en esta etapa; la purga de retención periódica (`DELETE WHERE recorded_at < threshold`) puede ejecutarse en lotes ligeros sin degradar el rendimiento del motor.

---

## 6. Verificación de Compatibilidad del Backend

Durante la inspección se verificó que:
1. El mapeador [IngestarTelemetriaUseCase](file:///home/agustin/proyectos_software/datamaq-telemetry/src/application/use_cases/ingestar_telemetria.py) procesa correctamente la estructura de arreglos `f: [{"n": "R", ...}]`.
2. Las columnas de ingeniería añadidas al modelo (`installation_type`, `phases_with_ct`, `desbalance_tension_porcentaje`, `voltage_linea_V`, `tension_neutro_estimada`) fueron sincronizadas en la base de datos de producción mediante Alembic (`alembic upgrade head`).
3. El servicio `datamaq-telemetry.service` persiste las mediciones instantáneas y de energía sin generar errores de deserialización.
