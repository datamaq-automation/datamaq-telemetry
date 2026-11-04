# Alta de medidor PRO15: cooperativa aceitera (borrador)

**Fecha:** 2026-11-03
**Estado:** borrador. Faltan datos del dueño (sección 1). No se ejecutó nada en producción.
**Relacionados:** [`../seguridad/plan-migracion-credenciales-mqtt.md`](../seguridad/plan-migracion-credenciales-mqtt.md) (etapa 4), [`../provisioning_guide.md`](../provisioning_guide.md), `specs/modelo-tecnico-cooperativas.md` (repo padre)

## 1. Datos pendientes (solo el dueño puede darlos)

| Campo | Valor |
|-------|-------|
| Nombre de la cooperativa | `<PENDIENTE>` |
| `organization_id` | `<PENDIENTE>` |
| Plantas (nombre e ID) | `<PENDIENTE>` |
| Distribuidora y tarifa de cada planta | `<PENDIENTE>` (no asumir) |
| Cantidad de PRO15 | `<PENDIENTE>` |
| `device_uid` (MAC) de cada PRO15 | `<PENDIENTE>` |
| Equipo en sitio o configuración remota | `<PENDIENTE>` |
| Tablero donde va cada medidor (TGBT / TS / CCM) y carga que mide | `<PENDIENTE>` |
| Plan: cooperativa, sin suscripción, límites aplicables | `<PENDIENTE>` |

## 2. Decisión de credenciales (aprobada 2026-11-03)

- Cada PRO15 tiene **usuario MQTT propio** (`device_uid`) y una contraseña generada para ese equipo. No se usa `datamaq_device`.
- **Prerrequisito técnico:** el usuario y su ACL en el broker se crean en el VPS, con autorización del dueño. Hoy el broker no tiene ACL por dispositivo, así que esta parte depende de la etapa 0 y 3 del plan de seguridad.
- Hasta que exista ese usuario, **el alta queda bloqueada**. No se aprovisiona con `datamaq_device` "por ahora", porque eso es lo que la auditoría marcó como ROJO.
- La contraseña se guarda fuera del repo (gestor de secretos del dueño). No aparece en logs, reportes ni este documento.

## 3. Pasos del alta (en orden)

1. **Inventario y usuario MQTT:** crear el usuario del PRO15 y su ACL en el VPS. Requiere autorización del dueño. Rollback: quitar el usuario.
2. **Aprovisionamiento:** `scripts/provision_device.py` con perfil `profiles/datamaq_server.json` y `--mqtt-username <device_uid>`. La contraseña se pasa por variable de entorno, no por línea de comandos.
3. **Verificación de conexión:** el equipo aparece en `mosquitto.log` con su usuario, y `/inst` y `/acc` llegan al backend.
4. **Auto-registro:** confirmar la fila en la tabla `devices` (solo lectura).
5. **Topología:** entrada de organización, planta y nodo en `data/organizaciones.yml` (repo `datamaq-data`). Lo hace la sesión de ese repo, no esta.
6. **Validación:** `python scripts/validate_topology.py` sin inconsistencias.
7. **Facturas:** se cargan por planta, con la distribuidora confirmada en el punto 2 de la sección 1.

## 4. Qué hace cada sesión

- **Esta sesión (`datamaq-telemetry`):** redacta, verifica el perfil y el script de aprovisionamiento, y corre tests. No toca producción ni el repo `datamaq-data`.
- **Sesión del repo `datamaq-data`:** carga la topología (paso 5).
- **Sesión DevOps del VPS:** crea el usuario MQTT y la ACL (paso 1), y verifica la conexión (paso 3). Solo con autorización del dueño, en la sesión que ejecuta.

## 5. Criterios de aceptación

- [ ] Cada PRO15 con usuario propio, sin `datamaq_device`.
- [ ] Telemetría de todos los medidores visible en el backend.
- [ ] Topología validada sin inconsistencias.
- [ ] Facturas cargadas por planta, con la distribuidora confirmada.
- [ ] Ninguna credencial en el repo, en logs ni en reportes.
