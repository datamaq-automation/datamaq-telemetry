# Plan: conectar los medidores SmartPlus de Unión Papelera Platense al servidor Datamaq

## Contexto

Sesión del 2026-09-11: se prepara la migración de dos medidores SmartPlus instalados en la planta
de la **Cooperativa de Trabajo Unión Papelera Platense Ltda.** (contacto:
`unionpapeleraplatense@hotmail.com`), actualmente apuntando a la configuración de fábrica
(`mqtt.powermeter.com.ar`), hacia el servidor propio `mqtt.datamaq.com.ar:8883`.

Es el mismo procedimiento ya documentado en [`docs/provisioning_guide.md`](./provisioning_guide.md)
y ya ejecutado antes con el medidor doméstico (`D48C49F03564`) y en el plan de
[Vajillas Durax](./plan-conexion-medidor-vajillas-durax.md). La diferencia relevante en este caso:
**la conectividad a internet de la planta depende de un módem Wi-Fi 4G**, cuyo estado de crédito/datos
se desconoce — puede ser el punto de falla antes de llegar siquiera al broker.

## Datos aún no confirmados (a resolver en el campo)

- ~~**MAC / Client ID de cada uno de los dos medidores.**~~ Medidor #1 confirmado (ver hallazgos
  2026-09-11 abajo). **Medidor #2 aún no localizado.**
- ~~**Estado de aprovisionamiento previo**~~ Medidor #1: ya unido a la red del módem 4G (además
  sigue emitiendo su AP de fábrica `Powermeter-D48C49F03724` en paralelo, modo AP+STA típico del
  firmware ESP32 — no hay que tocar ese AP).
- ~~**Crédito/saldo de datos del módem 4G**~~ Verificado 2026-09-11: hay datos y el broker
  `mqtt.datamaq.com.ar:8883` es alcanzable (ver hallazgos abajo). Riesgo descartado.
- Nombre definitivo de la planta para el alta en la base (se usa "Planta Principal UPP" como
  placeholder abajo — ajustar si corresponde otro nombre).

### Hallazgos de campo — 2026-09-11

- Conectado a la red del módem 4G (`D926_WINGLE_9E29`, WPA2). El módem asigna `192.168.0.0/24`
  (gateway `192.168.0.1`); el panel admin del módem requiere credenciales que no se tienen a mano
  (queda pendiente si hace falta ver señal/operadora en detalle).
- Verificación de datos del módem: `ping mqtt.datamaq.com.ar` → 0% pérdida, ~42ms; handshake TLS a
  `mqtt.datamaq.com.ar:8883` exitoso con cadena de certificados válida (Let's Encrypt). **El módem
  tiene conectividad completa a internet y al broker.**
- Barrido `192.168.0.0/24` (ping a las 254 IPs): solo 4 hosts vivos — `.1` (router/módem), `.100`,
  `.101`, `.105` (esta notebook).
  - `192.168.0.100` — confirmado **SmartPlus** (`data-theme="powermeter"`, `theme-color #04C4A4`
    en `http://192.168.0.100/`). MAC `d4:8c:49:f0:37:24` → **Client ID `D48C49F03724`** (medidor
    #1).
  - `192.168.0.101` — MAC `aa:29:48:0f:a8:2a` (localmente administrada / aleatoria, típica de un
    celular), interfaz web genérica sin el tema `powermeter`. **No es un medidor** — descartado.
  - Escaneo Wi-Fi de APs en el aire: solo apareció `Powermeter-D48C49F03724` (mismo MAC/equipo que
    `.100`, no un segundo medidor).
- **Medidor #2: no localizado.** Ni en la LAN del módem ni como AP de fábrica propio. Hipótesis:
  apagado, sin alimentación, o aún no instalado físicamente en planta — a confirmar in situ.
- **Medidor #1 aprovisionado con perfil Datamaq** (`mqtt.datamaq.com.ar:8883`, TLS-SERVER-AUTH, CA
  `isrg_root_x1.pem`, usuario `datamaq_device`) vía `scripts/provision_device.py --profile datamaq
  --reboot`. Configuración confirmada correcta en el propio equipo (`status.json`,
  `mqtt_config.json`, `mqtt_ca_certificate_config.json`) pero **sin conexión exitosa al broker**
  tras varios reintentos y reinicios.
- **Causa raíz encontrada: el módem 4G se quedó sin servicio celular ("Sin servicio" en su panel
  admin) durante la sesión.** No es un problema de DNS, ni de TLS/CA, ni de aislamiento de
  clientes en la red Wi-Fi del módem (confirmado desde el panel: el medidor figura reconocido
  normalmente en "Dispositivos conectados", sin entradas en la lista negra). Al inicio de la
  sesión el módem sí tenía datos (ping y TLS al broker funcionaban desde una notebook en la misma
  red), pero la señal se fue degradando (pérdida de paquetes intermitente, timeouts crecientes al
  HTTP del medidor) hasta caer a "Sin servicio" — coincide con que el medidor nunca haya logrado
  ni un solo intento de conexión TCP al broker (`Rx 0MB / Tx 0.02MB` en el panel del módem).
- **No requiere acción de software adicional.** El medidor #1 ya quedó con la configuración
  correcta apuntando a Datamaq; en cuanto vuelva el servicio celular del módem debería conectar
  solo. Pendiente en planta: revisar antena/ubicación del módem, saldo/estado de la SIM, o
  contactar al operador celular.

## Objetivo

Conectar ambos medidores al servidor propio (`mqtt.datamaq.com.ar:8883`) y verificar que reporten
telemetría real en el portal para el usuario de UPP.

## Pre-requisito operativo

Confirmar la red activa antes de cada paso:

```bash
nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes' || iwgetid -r
```

Si el módem 4G expone su propio Wi-Fi, vamos a estar en esa red al tocar cada medidor (no en la del
medidor directamente, salvo que aún estén en modo fábrica con su propio AP).

## Plan de ejecución

### 0. Verificar el módem 4G antes de tocar los medidores

- Confirmar que el módem tiene señal y datos disponibles (panel de administración del módem, o
  ping desde un equipo conectado a su Wi-Fi hacia `mqtt.datamaq.com.ar`).
- Si el módem no tiene crédito/datos, ningún medidor va a poder conectar sin importar cómo se lo
  configure — resolver esto primero evita diagnósticos cruzados en el paso 4.

### 1. Confirmar conectividad de red y ubicar cada equipo

- `nmcli`/`iwgetid` para confirmar la red activa.
- Barrido de ping + escaneo del puerto 80 (servidor web del ESP32) en la subred del módem 4G (ver
  §3.2 de [`docs/troubleshooting-conectividad-dispositivos.md`](./troubleshooting-conectividad-dispositivos.md)).
- Confirmar identidad de cada equipo por su interfaz web (`http://<ip>/`, tema `powermeter`,
  color `#04C4A4`) antes de tocar nada, y anotar su MAC (Client ID).

### 2. Dar de alta la organización/planta/dispositivos en la base

**Ya adelantado el 2026-09-11** (vía `ssh vps`): se creó la organización
`Cooperativa de Trabajo Unión Papelera Platense Ltda` y la planta `Planta Principal UPP`.

Falta agregar los dispositivos cuando se releven las MACs en el campo:

```bash
python3 scripts/seed_cliente.py \
  --org-nombre "Cooperativa de Trabajo Unión Papelera Platense Ltda" \
  --planta-nombre "Planta Principal UPP" \
  --dispositivo <MAC_MEDIDOR_1> "SmartPlus Trifásico #1" \
  --dispositivo <MAC_MEDIDOR_2> "SmartPlus Trifásico #2" \
  --usuario <email_operador_si_corresponde>
```

El script es idempotente: al repetir `--org-nombre`/`--planta-nombre` iguales reutiliza la
organización y planta ya creadas, y solo agrega los `--dispositivo` nuevos. Completar
`<MAC_MEDIDOR_1>` / `<MAC_MEDIDOR_2>` en el campo; usar `--dry-run` primero si hay dudas.

### 3. Aprovisionar el broker Datamaq en cada medidor

**Medidor #1 (`D48C49F03724`): hecho el 2026-09-11.** Config aplicada y verificada correcta;
pendiente solo de que el módem recupere servicio celular (ver hallazgos arriba) para que conecte.
**Medidor #2: pendiente** — aún no localizado en planta.

**Preferido — Método 1 automatizado** (`docs/provisioning_guide.md`, §"Método 1"), uno por vez:

```bash
export MQTT_PASSWORD='<contraseña de datamaq_device, en .env del VPS>'
python3 scripts/provision_device.py --profile datamaq --reboot
```

El script valida la configuración antes de enviarla (rechaza puerto 1883, TLS sin CA, credenciales
faltantes).

**Alternativa manual** (si el equipo no responde a la API del script): Método 2 de la misma guía,
vía `http://<ip>/home.html` (usuario `admin` / contraseña `powermeter`), sección MQTT:

| Parámetro | Valor |
|---|---|
| Broker Host | `mqtt.datamaq.com.ar` |
| Puerto | `8883` |
| Seguridad | `TLS-SERVER-AUTH` |
| CA | contenido de `isrg_root_x1.pem` (repo, raíz) |
| Usuario | `datamaq_device` |
| Contraseña | `MQTT_PASSWORD` del `.env` de producción |
| Client ID | MAC del equipo (una por medidor) |

> [!WARNING]
> No dejar el campo de CA vacío al guardar si el equipo ya tenía uno cargado — lo borra y rompe
> el TLS.

### 4. Auditar credenciales Wi-Fi si algún equipo no se asocia

```bash
python3 scripts/provision_device.py --wifi-audit
```

Para descartar homóglifos no-ASCII en SSID/contraseña del módem 4G (incidente ya documentado con
otro cliente, ver `docs/troubleshooting-conectividad-dispositivos.md`).

### 5. Verificar desde el servidor (vía `ssh vps`)

```bash
./scripts/logs.sh --mqtt --device <MAC_MEDIDOR_1>
./scripts/logs.sh --mqtt --device <MAC_MEDIDOR_2>
```

Confirmar en el broker una línea `New client connected ... as <MAC>` (no solo el eco de comandos
salientes del backend), y en la app logs de `mqtt_mensaje_recibido` con tópicos `inst`, `acc`,
`energyio` reales.

### 6. Verificar en la base de datos

Confirmar filas nuevas en `telemetry_instantaneous`/`telemetry_energy` para cada `device_uid`.

### 7. Verificación end-to-end en el portal

Con el usuario de UPP: seleccionar cada dispositivo y confirmar que el monitor en vivo muestra
potencia real (no cero, no "sin datos").

## Migración completada — 2026-09-11

Tras cambiar el chip SIM del módem 4G (el anterior se había quedado sin servicio celular, ver
hallazgos arriba), ambos medidores fueron localizados, dados de alta y aprovisionados, y
**confirmaron telemetría real end-to-end**:

- ✅ **Medidor #1** — `D48C49F03724` ("Trafo abajo", S/N 371). Conectado al broker
  (`New client connected ... u'datamaq_device'`), topic `inst` recibido y persistido:
  `p_activa_W: 7171.0`, `fp: 0.12`.
- ✅ **Medidor #2** — `ECC9FFB45488` ("Trafo arriba", S/N 370). Localizado conectado vía un
  repetidor Wi-Fi (`TP-Link_Extender`) que extiende la misma red del módem 4G — no estaba en el
  barrido inicial porque su AP de fábrica no llegaba con señal hasta la notebook. Conectado al
  broker, topic `inst` recibido y persistido: `p_activa_W: 2332.0`, `fp: 0.06`.
- IPs de LAN reasignadas para evitar colisión: medidor #1 fijado a `192.168.0.150` (estática, DNS
  `8.8.8.8`/`1.1.1.1` por el DNS roto del módem — ver hallazgos), medidor #2 quedó por DHCP en
  `192.168.0.100`. Documentar esto si se vuelve a tocar la config de red de cualquiera de los dos.

**Pendiente (no bloqueante):** paso 7 — verificación visual en el portal con el usuario de UPP
(`unionpapeleraplatense@hotmail.com`) para confirmar que el monitor en vivo muestra ambos
dispositivos. El factor de potencia bajo (`fp` 0.12 y 0.06) en ambos medidores llamó la atención —
vale la pena confirmar con el cliente si es esperado para esas cargas o si merece revisión aparte.

## Notas

- El costo de datos del módem 4G puede ser un factor operativo continuo (no solo de la puesta en
  marcha) — si el reporte de telemetría es muy frecuente, vale la pena revisar consumo de datos
  estimado vs. plan contratado una vez que ambos medidores estén reportando de forma estable.
- El aislamiento multi-tenant (WebSocket + REST) ya garantiza que un usuario de UPP solo vea sus
  propios dispositivos — no hace falta ningún cambio adicional de permisos una vez que el alta de
  la organización esté hecha y los equipos transmitiendo.
- Este documento es un plan operativo/de campo. Si en el proceso aparece un bug de software nuevo,
  documentarlo aparte (ver convención de `docs/troubleshooting-conectividad-dispositivos.md` §4,
  "Incidente ...").
