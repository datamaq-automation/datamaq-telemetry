# Spec — Aprovisionamiento MQTT con credenciales y CA TLS

## 1. Objetivo y Contexto

El perfil de aprovisionamiento `profiles/datamaq_server.json` apunta hoy a un
broker local (`192.168.4.2:1883`, `NO-SECURITY`, sin usuario/contraseña). Para
migrar los medidores Powermeter al VPS de Datamaq Telemetry se requiere:

- Broker con **TLS** (`8883`) y autenticación de usuario (`allow_anonymous false`).
- El script `scripts/provision_device.py` no permite inyectar credenciales MQTT
  ni un certificado CA por archivo, por lo que el medidor no podría autenticarse
  ni validar el certificado del servidor.

**Alcance:** extender el CLI de aprovisionamiento para enviar
`username`/`password` y el certificado CA (PEM) al medidor, y actualizar el
perfil `datamaq_server.json` a la postura de producción (TLS-SERVER-AUTH,
puerto `8883`). No se toca `src/` (no es parte del dominio de la plataforma).

## 2. Dominio & Puertos (Contrato del medidor)

El medidor Powermeter expone dos endpoints HTTP (Basic Auth `admin`/`powermeter`):

| Endpoint | Método | Payload | Semántica |
| :-- | :-- | :-- | :-- |
| `/mqtt_config.json` | POST | `mqtt_config` (ver abajo) | Configuración MQTT del equipo |
| `/mqtt_ca_certificate_config.json` | POST | `{"ca_certificate": "<PEM>"}` | CA raíz para `TLS-SERVER-AUTH` |

Campos de `mqtt_config`:

```text
enable_mqtt, enable_extended_topics, broker_host, broker_port,
username, password, security (NO-SECURITY | TLS-SERVER-AUTH),
clean_session, wifi_ack_timeout, wifi_keepalive,
mobile_ack_timeout, mobile_keepalive, connection_preference,
psk_identity, psk_key
```

## 3. Casos de Uso & DTOs (merge de configuración)

`apply_profile(host, profile_name, custom_host, custom_port, custom_security, custom_username, custom_password, custom_ca_file, user, password, reboot)`:

1. Carga el perfil JSON (`datamaq` o `powermeter-official`).
2. **Merge de sobreescritura** sobre `mqtt_config`:
   - `custom_host` → `broker_host`
   - `custom_port` → `broker_port` (int)
   - `custom_security` → `security`
   - `custom_username` (si es truthy) → `username`
   - `custom_password` (si es truthy) → `password`
3. **CA**: si `custom_ca_file` se provee, lee el archivo y usa su contenido como
   `ca_certificate`; en caso contrario usa `mqtt_ca_certificate` del perfil.
4. POST `/mqtt_config.json` y `/mqtt_ca_certificate_config.json`.
5. Si `reboot` → POST `/reboot.json`.

CLI: flags `--mqtt-username`, `--mqtt-password`, `--mqtt-ca-file` (default: sin
sobrescritura). Los secretos **no** se hardcodean en el perfil ni en el script.

## 4. Matriz de Pruebas (RED Suite)

| ID | Escenario | Contrato de test |
| :-- | :-- | :-- |
| P1 | `apply_profile` con `custom_username`/`custom_password` | El POST a `mqtt_config.json` incluye `username` y `password` inyectados |
| P2 | `apply_profile` con `custom_ca_file` | El POST a `mqtt_ca_certificate_config.json` lleva el contenido del PEM |
| P3 | `apply_profile` sin flags de credenciales | `username` y `password` permanecen con los valores del perfil (vacíos) |
| P4 | `--help` del CLI | La ayuda muestra `--mqtt-username`, `--mqtt-password`, `--mqtt-ca-file` |
| P5 | Perfil `datamaq_server.json` | `security == "TLS-SERVER-AUTH"` y `broker_port == 8883` |
| P6 | Perfil `datamaq_server.json` | `username == ""` y `password == ""` (sin secretos hardcodeados) |

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` (etapas 1-4): integridad, `ruff`, `pyright`, tests con
  cobertura `>= 85%`.
- `./scripts/ci.sh` (opcional): integración.
