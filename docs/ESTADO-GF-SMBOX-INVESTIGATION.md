# Estado actual: Integración GF-SMBOX-PLUS

**Fecha:** 2026-09-25
**Estado:** 🟡 EN STAND BY — bloqueador de origen resuelto, falta vincular cuenta Smart Life a un proyecto Tuya IoT Platform (requiere navegador; laptop de trabajo con recursos limitados)

---

## Resumen ejecutivo

El GF-SMBOX-PLUS **funciona correctamente** en Smart Life y **se descubre por broadcast local**. El bloqueo real no era de cuenta ni de dispositivo, sino que el script de extracción usaba un método de login de Tuya que fue deprecado. Ya se corrigió el script; falta crear el proyecto Cloud y vincular la cuenta desde un navegador con más recursos.

---

## Datos conocidos del dispositivo

- **Modelo:** GF-SMBOX-PLUS (Gralf, distribuidor)
- **Especificaciones:** 16A máximo, WiFi 2.4GHz
- **MAC:** `cc:8c:bf:bf:6d:24`
- **Red:** WiFi "Maestros" (subred real `10.0.20.0/24`, contraseña en gestor de secretos del usuario)
- **IP actual (2026-09-25):** `10.0.20.31` (dinámica, puede cambiar)
- **Device ID (gwId):** `eb9195f0784612c29cy6dd`
- **Versión de protocolo Tuya:** 3.4 (requiere Local Key para control local)
- **Estado:** Conectado y controlable desde Smart Life

---

## Bloqueador ORIGINAL (descartado)

Se sospechó que el dispositivo estaba vinculado a una cuenta Google OAuth
distinta de `agustin.deoz@gmail.com`, o que nunca se había registrado en la
API de Tuya.

**Se descartó por completo:** tras reset físico y re-vinculación en la red
WiFi real "Maestros" (no en la red/túnel que usaba la laptop originalmente),
el dispositivo se descubre sin problemas por broadcast UDP local
(`tinytuya.deviceScan()`).

**Detalle de red que generó confusión:** la laptop de trabajo no estaba
conectada por WiFi a "Maestros" sino accediendo a otra subred
(`10.194.124.0/24`) vía una interfaz Ethernet/túnel (acceso remoto). El
descubrimiento por broadcast UDP no atraviesa routers/VPN — requiere estar en
el mismo dominio L2 que el dispositivo. Al conectar la WiFi de la laptop
directamente a "Maestros", el descubrimiento funcionó al instante.

---

## Causa raíz REAL del bloqueador de Local Key

`scripts/extract_tuya_credentials.py` usaba `tinytuya.Cloud()` con
`apiKey`/`apiSecret` dummy, confiando en un login directo con usuario y
contraseña de Smart Life (truco no oficial, históricamente funcional).
**Tuya lo deprecó**: la API Cloud ahora siempre valida el `client_id`, y sin
uno real de un proyecto registrado, falla con:

```
Error: 'Unable to Get Cloud Token'
Payload: "Cloud _gettoken() failed: 'clientId is invalid'"
```

Confirmado en las 5 regiones (sa/us/eu/cn/in) — mismo error en todas, lo que
confirma que es un problema de credenciales de API (no de cuenta, dispositivo
ni región).

---

## Corrección ya aplicada en el repo

- `scripts/extract_tuya_credentials.py`: reescrito para usar
  `tinytuya.Cloud(apiKey=<Access ID>, apiSecret=<Access Secret>)` — la API
  Cloud oficial, en vez del login usuario/contraseña deprecado.
- `.env.example`: agregadas `TUYA_API_REGION`, `TUYA_ACCESS_ID`,
  `TUYA_ACCESS_SECRET`. Ya **no se usan** `TUYA_EMAIL`/`TUYA_PASSWORD`.
- `.env` local del usuario: ya tiene `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET`
  cargados (proyecto Cloud ya creado en https://iot.tuya.com).

---

## Paso pendiente (bloqueador actual): vincular cuenta Smart Life al proyecto

El Access ID/Secret del proyecto Cloud **no alcanza por sí solo**: el
proyecto necesita que la cuenta Smart Life (`agustin.deoz@gmail.com`) esté
vinculada a él para poder ver sus dispositivos.

**Proceso (requiere navegador + celular con Smart Life):**

1. Entrar al proyecto Cloud en https://iot.tuya.com.
2. Ir a la pestaña **"Devices"** dentro del proyecto (no en el menú superior
   de la cuenta — ese tiene Overview/App/Cloud/etc. a nivel plataforma).
3. Buscar la opción **"Link Tuya App Account"** (puede estar como botón
   directo o como sub-tab "App Account"). Muestra un código QR.
4. En la app Smart Life (celular, sesión `agustin.deoz@gmail.com`): perfil
   ("Me") → ícono de escaneo (esquina superior derecha) → escanear el QR.
5. Confirmar la vinculación en la app.
6. El proyecto Cloud debería listar los dispositivos de la cuenta,
   incluyendo el GF-SMBOX-PLUS.

**Motivo del stand by:** la laptop disponible tiene recursos limitados
(CPU/RAM) y hace muy difícil navegar el panel de Tuya IoT Platform (interfaz
pesada). Se retoma este paso con un equipo con más recursos, o desde el
celular/tablet si el panel de Tuya tiene versión liviana/móvil viable.

---

## Próximos pasos (al retomar)

1. Vincular cuenta Smart Life al proyecto Cloud (paso de arriba), desde un
   equipo con más recursos.
2. Correr `.venv/bin/python scripts/extract_tuya_credentials.py` (lee
   `TUYA_ACCESS_ID`/`TUYA_ACCESS_SECRET`/`TUYA_API_REGION` desde `.env`).
3. Confirmar que devuelve el Local Key del GF-SMBOX-PLUS
   (Device ID ya conocido: `eb9195f0784612c29cy6dd`).
4. Crear `scripts/bridge_tuya_mqtt.py` (traductor Tuya local ↔ MQTT,
   publicando al broker `mqtt.datamaq.com.ar:8883`).
5. Implementar modelo de alivio de carga en el backend (endpoints, lógica).
6. Testing (sin internet, latencia, reconexión, edge cases).
