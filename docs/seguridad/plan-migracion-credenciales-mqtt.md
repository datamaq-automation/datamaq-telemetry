# Plan de migración: credenciales y ACL del broker MQTT

**Fecha:** 2026-11-02
**Estado:** propuesta, pendiente de decisión del dueño (ver sección 1)
**Origen:** [`auditoria-hardening-2026-11-02.md`](auditoria-hardening-2026-11-02.md), hallazgos H1, H2 y H6
**Repos afectados:** `datamaq-telemetry` (backend, scripts de aprovisionamiento, docs). VPS (broker, ACL, firewall). Firmware de medidores (solo si se elige mTLS).

---

## 1. Decisión propuesta (para registrar en el repo padre)

> **Decisión propuesta:** cada medidor tiene su propia credencial MQTT y su ACL limitada a sus tópicos. El backend usa un usuario propio, separado del de los medidores. El usuario compartido `datamaq_device` se retira al final de la migración.
>
> **Justificación:** con una credencial compartida y `topic readwrite #`, un solo medidor comprometido expone la flota entera, incluidos comandos. La ola de ataques a controladores de refrigeración de octubre–noviembre de 2026 muestra el patrón: acceso remoto con credencial débil o compartida y sin límite de alcance.
>
> **Consecuencias:** los medidores en campo se reaprovisionan uno por uno (`scripts/provision_device.py --mqtt-username ... --mqtt-password ...`). Durante la migración conviven el usuario viejo y los nuevos, y la ingesta no se corta.

Para el repo padre, la entrada de `TODO.md` y la decisión en `decisions/` las redacta la orquestación. Este documento contiene el texto de referencia.

## 2. Principios

1. **Ninguna etapa corta la ingesta.** El usuario viejo sigue funcionando hasta que el último medidor esté migrado.
2. **Cada etapa tiene rollback**, documentado antes de ejecutarla.
3. **Cambios en producción requieren autorización explícita del dueño**, en la sesión que los ejecuta. La orquestación no los ejecuta ni los retransmite.
4. **Ninguna credencial aparece en el repo, en logs ni en reportes.** Solo nombres de usuario y estado.

## 3. Etapas

### Etapa 0: inventario (solo lectura, sin autorización adicional)

- Contenido de `/etc/mosquitto/acl` completo, con reglas por usuario.
- Usuarios de `/etc/mosquitto/passwd` (solo nombres).
- Dispositivos que se conectan hoy como `datamaq_device`: desde `mosquitto.log`, IP y client ID (MAC) por conexión, de las últimas 72 h.
- Si el staging usa `datamaq-telemetry-dev` o `datamaq-api-dev-ro`: revisar `/var/www/datamaq-telemetry-dev/.env` (solo nombres de variables) y los logs del servicio `datamaq-telemetry-dev.service`.
- Contrato de tópicos real: qué tópicos publica cada medidor y cuáles consume el backend. Sale de `src/infrastructure/paho_mqtt/mqtt_listener.py` y de los logs.

**Criterio de salida:** tabla de usuarios, tópicos y clientes conectados. Sin esta tabla no se escribe la ACL.

### Etapa 1: retirar los usuarios `-dev` (si no los usa nadie)

- **Condición:** la etapa 0 confirma que ni el staging ni ningún cliente los usa.
- **Acción:** quitar los usuarios de `passwd` y de la ACL. Recargar Mosquitto.
- **Rollback:** restaurar `passwd` y `acl` desde copia previa. Recargar.
- **Autorización:** del dueño (cambio en producción).

Si el staging sí los usa, se dejan con permisos mínimos y se documenta.

### Etapa 2: usuario propio para el backend y ACL del backend

- Crear `datamaq-backend` con permiso de lectura de los tópicos de medidores y sin escritura a esos tópicos.
- Cambiar `MQTT_USERNAME` y `MQTT_PASSWORD` del `.env` del backend (`/var/www/datamaq-telemetry/.env`) al nuevo usuario.
- Reiniciar `datamaq-telemetry.service`.
- **Verificación:** `mosquitto.log` muestra al backend conectado como `datamaq-backend`, y la ingesta persiste mensajes (consulta de solo lectura a la tabla de telemetría).
- **Rollback:** volver `MQTT_USERNAME=datamaq_device` en el `.env` y reiniciar.
- **Autorización:** del dueño. El reinicio corta la ingesta unos segundos.

### Etapa 3: ACL por dispositivo y usuario compartido en modo lectura

- Reemplazar `topic readwrite #` por reglas por dispositivo. Ejemplo orientativo, a confirmar con el contrato de tópicos de la etapa 0:
  ```
  pattern readwrite devices/%u/#
  ```
  El nombre de usuario de cada medidor tiene que coincidir con su identificador de tópico.
- **Riesgo:** los medidores actuales siguen con `datamaq_device`. Si la ACL les quita permiso a los tópicos que publican hoy, se corta la ingesta. Por eso esta etapa se hace **solo después de la etapa 4 para los medidores migrados**, o se hace en paralelo con una regla temporal para `datamaq_device` que conserve el alcance actual (documentar la regla temporal y su fecha de caducidad).
- **Rollback:** restaurar la ACL anterior y recargar.

### Etapa 4: aprovisionamiento por medidor (en campo o remoto)

- Por cada medidor: `scripts/provision_device.py` con `--mqtt-username <device_uid>` y una contraseña nueva, generada y guardada fuera del repo (gestor de secretos del dueño).
- `provision_device.py` ya expone `--mqtt-username` y `--mqtt-password` (`scripts/provision_device.py:337`). Para el modo `TLS-SERVER-AUTH` ya usa la CA de Let's Encrypt.
- Antes de cada medidor, registrar en un listado: `device_uid`, usuario creado, fecha, quién lo hizo. Sin contraseñas.
- **Verificación por medidor:** el medidor aparece en `mosquitto.log` con su usuario nuevo y su telemetría llega al backend.
- **Rollback por medidor:** volver a aprovisionarlo con `datamaq_device`. Mientras el usuario viejo exista, no hay corte.
- **Pendiente técnico:** confirmar con el firmware (SmartPlus / Powermeter) si acepta cambio de credenciales sin visita a campo. Si no, la etapa depende de visitas.

### Etapa 5: retirar `datamaq_device`

- **Condición:** ningún cliente conectado con ese usuario en 7 días (desde `mosquitto.log`).
- **Acción:** quitar el usuario de `passwd` y su regla de ACL.
- **Rollback:** volver a crear el usuario con una contraseña nueva y reaprovisionar lo que haga falta.
- **Autorización:** del dueño.

### Etapa 6 (opcional, a futuro): mTLS con certificados de cliente

- `require_certificate true` y CA propia para los medidores.
- Depende de que el firmware soporte certificados de cliente. Hoy no está confirmado.
- Se evalúa después de la etapa 5.

## 4. Firewall y kernel (fuera del alcance de MQTT, mismo reporte)

Hallazgos H3 y H5 de la auditoría. No son parte de la migración de credenciales, pero salen del mismo reporte:

- **Firewall (`table inet fwmin`):** restringir puertos de paneles de hosting (10000, 2082–2097) a IPs de administración. Los de correo (25, 110, 143, 465, 587, 993, 995, 4190) se evalúan por separado porque el servidor de correo puede ser de uso real. **Autorización del dueño.** Verificar antes de aplicar que no se cierra acceso de administración propio.
- **Kernel:** 7 paquetes de seguridad pendientes. Requiere reinicio del VPS. Programar en ventana de mantenimiento, con aviso previo a la ingesta de medidores (un reinicio corta el broker). **Autorización del dueño.**

## 5. Criterios de aceptación

- [ ] Etapa 0 entregada con la tabla de usuarios, tópicos y clientes conectados.
- [ ] Ningún usuario `-dev` sin uso activo en el broker de producción.
- [ ] Backend conectado con usuario propio, sin `datamaq_device`.
- [ ] Todos los medidores conectados con usuario propio, verificado en `mosquitto.log`.
- [ ] `datamaq_device` retirado, o con regla temporal documentada y fecha de caducidad.
- [ ] ACL sin `readwrite #` para ningún usuario de dispositivo.
- [ ] Ninguna credencial en el repo ni en reportes.
- [ ] Firewall y kernel: decisiones del dueño registradas.

## 6. Pruebas en el repo (`datamaq-telemetry`)

Antes de cambiar cualquier configuración en el VPS:

- Tests de `scripts/provision_device.py` con `--mqtt-username` distinto de `datamaq_device` (ya existe `tests/unit/test_provision_device.py`; agregar un caso con usuario por dispositivo).
- Tests del listener y del backend con `MQTT_USERNAME` distinto al default.
- Gauntlet local en verde (`APP_ENV=test ./scripts/pre-push.sh`) antes de cualquier push. Las pruebas de integración no corren en el CI de `develop`, solo en PR a `main`.

Las pruebas del repo no reemplazan la verificación en el VPS, que es la que confirma la ACL real.

## 7. Dependencias y preguntas abiertas para el dueño

1. **¿Autorizás la etapa 0 (inventario)?** Es solo lectura y no necesita autorización adicional, pero conviene confirmar.
2. **¿Los usuarios `datamaq-telemetry-dev` y `datamaq-api-dev-ro` los usa el staging o alguien más?** Lo resuelve la etapa 0.
3. **¿El firmware de los medidores permite cambiar credenciales de forma remota?** Define si la etapa 4 requiere visitas a campo.
4. **¿Autorizás el cambio de firewall (paneles de hosting) y la ventana de reinicio para el kernel?**
5. **¿Cuál es el contrato de tópicos oficial?** Sin él no se puede escribir la ACL por dispositivo.

## 8. Referencias

- [`auditoria-hardening-2026-11-02.md`](auditoria-hardening-2026-11-02.md)
- `docs/provisioning_guide.md`, `docs/troubleshooting-conectividad-dispositivos.md`, `profiles/datamaq_server.json`
- `scripts/provision_device.py`, `scripts/test_realtime_mode.py`
- `src/infrastructure/paho_mqtt/mqtt_listener.py`
- [CISA: default passwords](https://www.waterisac.org/cisa-urges-manufacturers-eliminate-default-passwords-thwart-cyber-threats)
