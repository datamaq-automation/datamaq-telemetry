# Plan: conectar el 2do medidor de Cooperativa Los Constituyentes al servidor Datamaq

## Contexto

Sesión del 2026-09-17: en planta de la **Cooperativa de Trabajo Los Constituyentes Ltda.**
(Planta San Martín) ya había un medidor operativo (`D48C49F035A8`, "TGBT Trafo 1"). El
segundo tablero (TGBT Trafo 2, transformador en reserva fría) figuraba en
`data/organizaciones.yml` sin medidor instalado.

## Hallazgos de campo — 2026-09-17

- Al reiniciar el equipo se detectó su AP de fábrica `Powermeter-ECC9FFB57F20`. Vía el portal
  (`http://192.168.4.1/home.html`, `admin`/`powermeter`) se confirmó un 2do medidor SmartPlus
  ya en operación:
  - `device_info.json`: `serial_number: "369"`, `user_email: marcelosoruco22@gmail.com`
    (responsable técnico de la cooperativa), `device_name: "Sala de trafo2"`, `device_model:
    SmartPlus`, `hw_model: HOME V2.0`.
  - Ya estaba conectado por Wi-Fi a la red del sitio ("Sala de transformadores",
    `172.16.0.116`) y por MQTT al broker de fábrica `mqtt.powermeter.com.ar:8884`.
- Aprovisionado con el perfil Datamaq (`scripts/provision_device.py --host 172.16.0.116
  --profile datamaq --reboot`): `mqtt.datamaq.com.ar:8883`, TLS-SERVER-AUTH, CA
  `isrg_root_x1.pem`, usuario `datamaq_device`.
- Verificado en la VPS tras el reinicio:
  - `mosquitto.log`: `New client connected ... as ECC9FFB57F20 ... u'datamaq_device'`.
  - Logs de la app: `mqtt_mensaje_recibido` con topic `acc` real.
  - El dispositivo ya existía en la tabla `devices` (`c91713f1-0621-4a33-9279-c5327a317d96`,
    `status=ONLINE`) pero con `facility_id` NULL — no estaba vinculado a ninguna planta.
- Asignado a la planta con:
  ```bash
  python3 scripts/seed_cliente.py \
    --org-nombre "Cooperativa de Trabajo Los Constituyentes Ltda." \
    --planta-nombre "Planta San Martín" \
    --asignar-dispositivo-existente ECC9FFB57F20
  ```
  Confirmado en BD: `facility_id` → Planta San Martín, `organization_id` →
  `20857cb6-eff2-4bd4-8cb9-36e4c63bcee3`.
- Actualizado `data/organizaciones.yml`: agregado el medidor `c91713f1-0621-4a33-9279-c5327a317d96`
  (alias `369`/`ECC9FFB57F20`), su layout en la zona de subestación, y vinculado
  `nodo-lc-tgbt-2` (`device_id`).

## Pendiente

- Verificación visual en el portal junto al responsable técnico de la cooperativa
  (`marcelosoruco22@gmail.com`) para confirmar que ve ambos dispositivos en el monitor en vivo.
- El transformador 2 sigue en reserva fría (apagado) — el medidor reporta pero sin carga
  significativa; no se calibraron fases/TI en este dispositivo (queda para cuando el
  transformador entre en servicio, si aplica).
