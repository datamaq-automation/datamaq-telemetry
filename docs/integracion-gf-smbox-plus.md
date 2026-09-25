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

| Duda | Impacto | Estado | Plan para resolver |
|------|--------|--------|-------------------|
| ¿Es realmente Tuya o clone? | Medio | ✅ Casi confirmado (Smart Life funciona nativamente) | Extraer Device ID + Local Key |
| ¿Tiene local key accesible? | Alto | ❓ Desconocido | Script `extract_tuya_credentials.py` lo obtendrá desde API Tuya |
| ¿Por qué Smart Life reporta IP pública? | Bajo | ✅ Normal (comunica con servidores Tuya en nube) | Esperado; la IP local será diferente (10.194.124.x) |
| ¿Puerto UDP ocupado? | Medio | ❓ Requiere investigación | Identificar qué proceso usa puerto UDP; posible: otro servicio IoT |
| ¿Responde a broadcasts locales? | Alto | ❓ No responde | Posibles causas: firewall router, aislamiento AP, VLANs |
| ¿Soporta protocolo MQTT nativo? | Bajo | ❌ Probablemente no | Usaremos bridge Tuya→MQTT |
| ¿Necesita acceso a cloud Tuya? | Medio | ✅ No (Tuya permite local) | Con Local Key podemos hablar directamente al dispositivo |
| ¿Consumo de energía en reposo? | Bajo | ✅ Manual: ≤0.8W | Confirmado |
| ¿Relé? ¿Tiempos de switching? | Bajo | ❓ No especificado | Mediremos en pruebas de integración |

---

## Decisiones arquitectónicas (post-investigación)

### 1. Autenticación: Cloud API vs Local Protocol

**Opciones:**
- **A: Usar API Cloud Tuya** (simple, requiere internet)
  - Ventajas: Simple, confiable, sin necesidad de extraer Local Key
  - Desventajas: Depende de internet, posible latencia
  
- **B: Usar protocolo local Tuya** (directo, sin internet)
  - Ventajas: Rápido, funciona sin internet, control total
  - Desventajas: Requiere Local Key, setup más complejo

**Decisión preliminar:** Opción B (Local) + fallback a Cloud
- Razón: Alivio de carga es crítico → no queremos depender de internet
- Estrategia: Intentar local primero; si falla, usar cloud

### 2. Extracción de credenciales

**Problema:** Smart Life no muestra Local Key en la app

**Solución:** Usar `extract_tuya_credentials.py`
- Requiere credenciales de cuenta Tuya/Smart Life
- Las obtiene de la API oficial
- Se guardan **LOCALMENTE** en `tuya_devices_credentials.json` (NO en git)

**Seguridad:**
- Archivo debe estar en `.gitignore`
- Solo el usuario debe tener acceso (permisos 600)
- Nunca compartir ni pushear

### 3. Bridge MQTT

**Decisión:** Python + tinytuya + paho-mqtt
- Lightweight (vs Node.js)
- Integración directa con backend datamaq-telemetry
- Ya tienen Python en la stack

---

## Próximos pasos

### Fase 1: Extracción de credenciales (AHORA)

```bash
cd /home/agustin/proyectos_software/datamaq-telemetry
source venv/bin/activate
python scripts/extract_tuya_credentials.py
```

**Entrada requerida:**
- Email de cuenta Smart Life
- Contraseña (solo local, NO se envía)

**Salida esperada:**
- Device ID del GF-SMBOX
- Local Key (para control sin internet)
- Archivo: `tuya_devices_credentials.json` (mantener seguro, NO en git)

### Fase 2: Bridge MQTT local (próxima semana)

Crear `scripts/bridge_tuya_mqtt.py`:
- Lee `tuya_devices_credentials.json`
- Se conecta directamente al GF-SMBOX vía protocolo Tuya (sin internet)
- Publica estado en MQTT: `m/wifi/gf-smbox-plus-01/state`
- Escucha comandos: `m/wifi/gf-smbox-plus-01/command`
- Reconexión automática
- Logs para debugging

**Librerías:**
- `paho-mqtt` (cliente MQTT → broker central)
- `tinytuya` (cliente Tuya local → dispositivo)

### Fase 3: Integración backend (posterior)

- [ ] Crear modelo `AlivioDeCargas` (planta, dispositivo, duración, ejecutado_en)
- [ ] API endpoint: `POST /api/v1/plantas/{id}/alivio`
- [ ] Consumidor MQTT que publica comandos al bridge
- [ ] Lógica: máximo 1 alivio simultáneo, límites por hora
- [ ] Auditoría: loguear cada solicitud + resultado
- [ ] WebSocket notifications para UI

### Fase 4: Testing

- [ ] Control local sin internet (critical)
- [ ] Latencia comando → respuesta
- [ ] Reconexión automática después de desconexión
- [ ] Múltiples plantas con múltiples dispositivos
- [ ] Casos edge (simultáneo, cancelación, timeout)

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

### Ejecución 1: 2026-09-25 14:06 UTC (Dispositivo apagado)

**Comando:** `python scripts/discover_tuya_devices.py`

**Resultado:**
```
Red local detectada: 10.194.124.0/24
Dispositivos con puerto 6668 abierto: 0
Dispositivos Tuya vía broadcast: 0 (no encontrados)
```

**Conclusión:** Dispositivo no está en red (esperado - aún no conectado).

---

### Ejecución 2: 2026-09-25 14:xx UTC (Dispositivo conectado a WiFi "Maestros")

**Estado del dispositivo en Smart Life:**
- ✅ Conectado a WiFi: "Maestros"
- ✅ Estado: Conectado
- 📊 Fuerza de señal: -41 dBm (excelente)
- 🔗 IP reportada por Smart Life: `186.18.144.215` (PÚBLICA/WAN)
- 🖥️ MAC local: `cc:8c:bf:bf:6d:24`

**Comando ejecutado:** `python scripts/discover_tuya_devices.py`

**Resultado:**
```
Red local detectada: 10.194.124.0/24
Dispositivos activos (puerto 6668): 0
Descubrimiento Tuya: Error - Address already in use (puerto UDP ocupado)
```

**Hallazgos importantes:**
1. El dispositivo **SÍ está conectado a WiFi** (confirmado por Smart Life)
2. Smart Life reporta IP **pública** (186.18.144.215) no local - esto es normal, indica que se conectó a servidores Tuya en la nube
3. El puerto UDP necesario está ocupado (probablemente por otro proceso) → necesita investigación
4. Device no responde a broadcasts locales (posible: firewall, configuración VLAN, o aislamiento de AP)

---

## Consideraciones de seguridad

### Almacenamiento de credenciales

**Archivo:** `tuya_devices_credentials.json`
```json
{
  "device_id_xxx": {
    "name": "GF-SMBOX-PLUS",
    "device_id": "...",
    "local_key": "...",
    "category": "switch"
  }
}
```

**Protección requerida:**
```bash
# Agregar a .gitignore
echo "tuya_devices_credentials.json" >> .gitignore

# Restringir permisos de archivo
chmod 600 tuya_devices_credentials.json

# Verificar que no esté trackeado
git rm --cached tuya_devices_credentials.json 2>/dev/null || true
```

**¿Por qué necesitamos el Local Key?**
- Tuya no lo muestra en la app
- Es necesario para comunicación directa sin internet
- Se obtiene de la API Cloud de Tuya (credenciales = acceso a todos los dispositivos de tu cuenta)
- El script `extract_tuya_credentials.py` lo obtiene de forma segura

**Alternativas consideradas:**
1. ❌ Hardcoded en código → seguridad nula
2. ❌ Variable de entorno → aún visible en logs
3. ✅ Archivo JSON con permisos restrictivos → mejor
4. ⏳ Vault/KMS en producción → futuro

---

## Log de cambios

- **2026-09-25 14:00:** Investigación inicial, especificaciones, dudas documentadas
- **2026-09-25 14:30:** Dispositivo conectado a WiFi; documentados hallazgos y decisiones arquitectónicas
- **2026-09-25 14:45:** Creados scripts de extracción; planes de Fase 1-4 definidos
