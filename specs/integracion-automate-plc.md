# Especificación Técnica: Integración del Powermeter Automate 24V-4M

## 1. Alcance y Contexto

Esta especificación define el diseño de ingesta, protocolo y enrutamiento para el autómata **Powermeter Automate 24V-4M** en la plataforma **Datamaq Telemetry**.

El Automate 24V-4M es un PLC industrial dual-core (ESP32) equipado con:
- 12 puertos digitales configurables E/S (P1 a P12).
- 12 entradas analógicas (0-10V / 4-20mA).
- 2 salidas analógicas (A1 y A2).
- Interfaces de comunicación: Ethernet (RJ45), Wi-Fi, RS485 (Modbus RTU), Modbus TCP.

---

## 2. Ingesta MQTT y Enrutamiento Multi-Tópico

### 2.1 Ampliación de Suscripciones en el Listener

Actualmente el backend escucha bajo el prefijo `MQTT_TOPIC_PREFIX = "m/wifi/#"`. Se extenderá para admitir suscripciones múltiples:
- `m/wifi/#` (Medidores de energía)
- `auto24v4m/#` (Autómatas 24V-4M)

### 2.2 Despacho por Namespace de Tópico

```
Tópico MQTT Entrada
  ├── m/wifi/<MAC>/<subtopic>     ──► IngestarTelemetriaUseCase (Mediciones Eléctricas)
  └── auto24v4m/<ID>/<subtopic>   ──► IngestarAutomateUseCase (Señales de E/S y Estado PLC)
```

---

## 3. Topología de Tópicos del Automate 24V-4M

| Tópico | Subtópico | Función |
|---|---|---|
| `auto24v4m/{id}/status/v1` | Status | Telemetría de conectividad (IP, RSSI, uptime, memoria) |
| `auto24v4m/{id}/inst/io/v1` | Telemetría I/O | Estado instantáneo de puertos digitales P1..P12 y analógicos A1..A2 |
| `auto24v4m/{id}/inst/block/v1` | Bloques Lógicos | Estado de bloques de función interna del PLC |
| `auto24v4m/{id}/onoff/v1` | Conexión / LWT | Notificación de encendido/desconexión |
| `auto24v4m/{id}/conf/com` | Comandos | Recepción de comandos remotos (salidas, setpoints) |
| `auto24v4m/{id}/conf/rta` | Respuestas | Confirmación de comandos aplicados |

---

## 4. Fusión de Estados de Disponibilidad (Smart Plus + Automate)

Cuando una `Maquina` tiene asociados tanto un medidor Smart Plus como un Automate:

1. **Estado de Marcha/Parada (Smart Plus):**
   - Calculado por la regla de potencia activa $P(t) > \text{on\_threshold\_w}$.
2. **Causal del Evento (Automate 24V-4M):**
   - Cuando la potencia cae por debajo del umbral de marcha y se activa una entrada digital del Automate (ej: P1=Paro Emergencia, P2=Falla Térmica, P3=Falta de Material):
   - El `EventoDisponibilidad` se registra con:
     - `estado`: `PARADA`
     - `tipo_parada`: `NO_PROGRAMADA`
     - `origen`: `AUTOMATA`
     - `comentario` / `notes`: Código o descripción de la señal física recibida desde el PLC.
