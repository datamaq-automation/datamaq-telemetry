# Guía de Configuración y Puesta en Marcha en Planta: Automate 24V-4M y Smart Plus

Este documento sirve como referencia completa para retomar la puesta en marcha de la nueva planta en cualquier dispositivo. Contiene el estado del software desplegado, los parámetros de configuración en sitio y el procedimiento paso a paso para el aprovisionamiento.

---

## 1. Contexto de la Planta y la Máquina

- **Activo Monitoreado:** Máquina **Confeccionadora de Bolsas**.
- **Medidor 1 (Smart Plus):** Medidor de potencia y energía eléctrica trifásico/monofásico dedicado exclusivamente a la confeccionadora.
- **Medidor 2 (Powermeter Automate 24V-4M):** PLC industrial conectado por cable Ethernet RJ45 a la red de planta y cableado a las señales de control de la máquina.
  - **Entrada Digital (Puerto P1):** Sensor/contador de producción de bolsas (pulsos por corte/soldadura).
- **Criterio de Disponibilidad por Ritmo de Producción (PPM):**
  - Frecuencia $\ge 30 \text{ piezas/bolsas por minuto (PPM)} \implies \text{MARCHA}$ (Máquina Operativa).
  - Frecuencia $< 30 \text{ PPM} \implies \text{PARADA}$ (Máquina Detenida / En Espera).
- **3er Medidor General:** Existente en planta, temporalmente diferido hasta resolver el acceso a sus datos.

---

## 2. Estado del Software Desplegado en la VPS

El backend en la VPS (`mqtt.datamaq.com.ar`) ya cuenta con las siguientes funcionalidades integradas y probadas en el commit `18a1740`:

1. **Suscripción Multi-Tópico:** Escucha simultáneamente `m/wifi/#` (medidores eléctricos) y `auto24v4m/#` (autómatas PLC).
2. **Caso de Uso de Ingesta Automate (`IngestarAutomateUseCase`):**
   - Auto-registro de equipos con modelo `"Automate24V4M"`.
   - Parseo de tramas JSON de puertos (`inst/io/v1`, `status/v1`, `onoff/v1`) en formato `dict` y `list`.
   - Cálculo de ventana deslizante de 60s para cadencia PPM sobre el contador de producción.
   - Transición automática de eventos de disponibilidad de máquina (`MARCHA` vs `PARADA`).
3. **Script de Aprovisionamiento Rápido en Sitio:** [`scripts/provision_confeccionadora.py`](file:///home/agustin/proyectos_software/datamaq-telemetry/scripts/provision_confeccionadora.py).

---

## 3. Pasos de Configuración en Campo (Presencial en Planta)

### Paso A: Migración de Broker MQTT en el Automate 24V-4M
1. Conectar la notebook o teléfono a la red del Automate (vía Ethernet o su punto de acceso Wi-Fi local `192.168.4.1`).
2. Acceder a la interfaz web local: `http://192.168.4.1` (o la IP asignada por DHCP Ethernet).
3. Navegar a **MQTT Settings** y actualizar:
   - **Broker Host:** `mqtt.datamaq.com.ar`
   - **Broker Port:** `8884` (o puerto TLS de producción)
   - **Topic Base:** `auto24v4m/{id}/`
4. Guardar y reiniciar el equipo.

### Paso B: Migración de Broker MQTT en el Smart Plus
1. Conectar al AP local del Smart Plus (`192.168.4.1`).
2. En la sección **MQTT Configuration**, actualizar:
   - **Broker Host:** `mqtt.datamaq.com.ar`
   - **Broker Port:** `8884`
3. Copiar las direcciones MAC / IDs de ambos equipos:
   - MAC Smart Plus (ej: `AABBCCDDEEFF`).
   - ID Automate (ej: `112233445566`).

---

## 4. Ejecución del Alta en la VPS (1 Comando)

Una vez obtenidas las MACs/IDs en planta, ingresar por SSH a la VPS y ejecutar el script idempotente de alta:

```bash
cd /ruta/al/proyecto/datamaq-telemetry
.venv/bin/python scripts/provision_confeccionadora.py \
  --smartplus-mac <MAC_SMARTPLUS> \
  --automate-id <ID_AUTOMATE> \
  --org "Cliente Confecciones" \
  --planta "Planta Principal" \
  --maquina "Confeccionadora de Bolsas"
```

El script se encarga de:
- Crear la Organización y la Planta si no existen.
- Registrar/vincular el Smart Plus y el Automate a la planta.
- Registrar la `Maquina` ("Confeccionadora de Bolsas") asociando las métricas de energía y el contador de producción.

---

## 5. Verificación de Funcionamiento

### Verificación de Logs en Vivo
En la VPS, transmitir los logs MQTT en tiempo real:
```bash
./scripts/logs.sh --mqtt
```
Se observarán mensajes de suscripción y recepción en `m/wifi/...` y `auto24v4m/...`.

### Consulta API REST de Disponibilidad y Métricas OEE
```bash
curl -X GET "http://localhost:8000/api/v1/disponibilidad/maquinas" \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 6. Próximos Pasos Futuros

- **Calibración del Umbral PPM:** Si la confeccionadora opera a velocidades distintas según el grosor/material de la bolsa, se puede ajustar el parámetro `umbral_marcha_ppm` desde el servicio de disponibilidad.
- **Integración del 3er Medidor:** Cuando se habilite la salida de datos del medidor de acometida general, agregarlo al diagrama `UnifilarPlanta` usando `scripts/seed_cliente.py`.
