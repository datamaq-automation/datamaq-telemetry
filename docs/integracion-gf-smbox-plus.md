# Integración GF-SMBOX-PLUS (Control de Alivio de Carga)

**Estado:** 🔍 Investigación inicial  
**Fecha inicio:** 2026-09-25  
**Última ejecución:** 2026-09-25 14:06 UTC (sin dispositivo en red)  
**Propósito:** Control de alivio de carga (load shedding) para plantas  
**Caso de uso:** Desconectar cargas automáticamente cuando la demanda lo requiera

---

## Resumen ejecutivo

El **GF-SMBOX-PLUS** es un interruptor WiFi inteligente de marca **Gralf** (distribuidor/reseller) que permite controlar cargas eléctricas hasta **16A**. Está basado en tecnología **Tuya** (confirmado por compatibilidad con Smart Life).

**Flujo propuesto:**
```
GF-SMBOX-PLUS (WiFi 2.4GHz)
    ↓ Configuración vía Smart Life app
    ↓
Bridge MQTT local (Python en laptop)  ← Traduce Tuya → MQTT
    ↓
Tu broker MQTT: mqtt.datamaq.com.ar:8883
    ↓
Backend datamaq-telemetry (consume comandos de alivio)
```

---

## Hallazgos de investigación

### 📦 Especificaciones técnicas

| Parámetro | Valor |
|-----------|-------|
| **Fabricante** | Gralf (distribuidor, no OEM) |
| **Modelo** | GF-SMBOX-PLUS |
| **Capacidad** | 16A máximo |
| **Voltaje** | 90-250V AC |
| **Conectividad** | WiFi 2.4GHz 802.11b/g/n |
| **Protocolo base** | Tuya (95% seguridad) |
| **App oficial** | Smart Life |
| **Compatibilidad** | Google Home, Alexa, IFTTT |

### ✅ Certezas

1. **Es compatible con Smart Life** → Implica protocolo Tuya
2. **Tuya tiene soporte local vía MQTT** → Existen bridges estables (tuya-mqtt, tinytuya, rust-tuya-mqtt)
3. **Puede recibir comandos ON/OFF** → Apto para alivio de carga
4. **WiFi local** → No necesita conexión a nube para control básico

### ❓ Incógnitas / Dudas

| Duda | Impacto | Plan para resolver |
|------|--------|-------------------|
| ¿Es realmente Tuya o clone?** | Medio | Verificar Device ID después de configurar en Smart Life |
| ¿Tiene local key accesible? | Alto | Script `discover_tuya_devices.py` lo buscará |
| ¿Soporta protocolo MQTT nativo? | Bajo | Probablemente no, usaremos bridge |
| ¿Necesita acceso a cloud Tuya? | Medio | Tuya permite modo "local only" con credenciales extraídas |
| ¿Consumo de energía en reposo? | Bajo | Manual dice ≤0.8W |
| ¿Relé? ¿Tiempos de switching? | Bajo | No especificado; lo mediremos en pruebas |

---

## Próximos pasos

### Fase 1: Validación (HOY)

```bash
# 1. Instalar descubridor
pip install tinytuya

# 2. Ejecutar descubrimiento
python scripts/discover_tuya_devices.py
```

**Esperamos obtener:**
- Device ID del GF-SMBOX
- IP local
- Versión del protocolo Tuya
- Local Key (si está disponible)

### Fase 2: Bridge MQTT (próxima semana)

Implementar bridge Python que:
- Se conecta al GF-SMBOX vía Tuya (usando Device ID + Local Key)
- Publica estado en `m/wifi/gf-smbox-plus-01/state` (JSON)
- Escucha comandos en `m/wifi/gf-smbox-plus-01/command`
- Traduce entre Tuya ↔ MQTT

**Librerías:**
- `paho-mqtt` (cliente MQTT)
- `tinytuya` (cliente Tuya local)

### Fase 3: Integración backend (posterior)

- Crear endpoint de "solicitar alivio de carga"
- Mapear plantas → GF-SMBOX-PLUS
- Lógica de activación/desactivación
- Auditoría de eventos

---

## Arquitectura propuesta

### Componentes

```
┌─────────────────────────────────────────────────────┐
│                 datamaq-telemetry                  │
│              (backend en VPS)                       │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  API: POST /api/v1/plantas/{id}/alivio      │  │
│  │       ├─ Activar alivio por N segundos     │  │
│  │       └─ Desactivar alivio                 │  │
│  └──────────────────────────────────────────────┘  │
│                       ↑                             │
│           MQTT: m/wifi/gf-smbox-plus-*/command     │
└─────────────────────────────────────────────────────┘
                        ↑
                        │ (TLS, puerto 8883)
          ┌─────────────┴──────────────┐
          │  MQTT Broker               │
          │  mqtt.datamaq.com.ar:8883  │
          └─────────────┬──────────────┘
                        ↑
          MQTT: m/wifi/gf-smbox-plus-*/state
                        │
                        │
        ┌───────────────┴────────────────┐
        │  Bridge MQTT local (Python)    │
        │  (corre en laptop/servidor)    │
        │                                │
        │  • Conecta a GF-SMBOX vía      │
        │    protocolo Tuya              │
        │  • Traduce commands ↔ estado   │
        │  • Publica en broker central   │
        └────────────────┬───────────────┘
                         │
                         ↓ (WiFi local)
        ┌────────────────────────────────┐
        │     GF-SMBOX-PLUS              │
        │  Interruptor WiFi 16A          │
        │  (control de carga)            │
        └────────────────────────────────┘
```

### Topics MQTT propuestos

```
m/wifi/gf-smbox-plus-01/
├── state       → {"power": "on", "current": 2.3, "voltage": 220}
└── command     ← {"action": "on"} | {"action": "off"}

m/wifi/gf-smbox-plus-02/
├── state
└── command
```

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Severidad | Mitigación |
|--------|-------------|-----------|-----------|
| GF-SMBOX no es Tuya-based | Baja | Alta | Descubridor lo verificará; si falla, investigar manual |
| Local key no accesible | Media | Alta | Usar mode fuerza bruta o contactar a Gralf |
| Latencia MQTT > 1s | Baja | Baja | Aceptable para alivio de carga (no crítico en tiempo real) |
| Dispositivo desconectado frecuentemente | Media | Media | Implementar reconexión automática en bridge |

---

## Referencias

- **Manual físico del GF-SMBOX-PLUS:** Disponible en el proyecto (información limitada)
- **Smart Life app:** https://apps.apple.com/es/app/smartlife-smart-living/id1115101477
- **Tuya Developer Docs:** https://developer.tuya.com/en/docs/iot/MQTT-protocol
- **Proyectos Tuya→MQTT:**
  - https://github.com/TheAgentK/tuya-mqtt (Node.js)
  - https://github.com/EmilSodergren/rust-tuya-mqtt (Rust)
  - tinytuya (Python, usaremos este)

---

## Hallazgos de ejecución

### Ejecución 1: 2026-09-25 14:06 UTC

**Comando:** `python scripts/discover_tuya_devices.py`

**Resultado:**
```
Red local detectada: 10.194.124.0/24
Dispositivos con puerto 6668 abierto: 0
Dispositivos Tuya vía broadcast: 0 (no encontrados)
```

**Conclusión:**
- El GF-SMBOX-PLUS **NO está actualmente en la red local**
- Causas posibles:
  1. Dispositivo apagado
  2. No conectado a WiFi
  3. Emparejamiento en Smart Life no completado
  4. En modo AP (punto de acceso) esperando configuración

**Acciones requeridas antes del próximo escaneo:**
1. Completar instalación en Smart Life (hasta que aparezca "Conectado" en verde)
2. Verificar que WiFi muestre "Conectado" en la app
3. Dispositivo debe estar alimentado (luz LED)
4. Esperar 30-60s después de encender antes de escanear

---

## Log de cambios

- **2026-09-25:** Investigación inicial, especificaciones, dudas documentadas; primer escaneo sin dispositivo (esperado)
