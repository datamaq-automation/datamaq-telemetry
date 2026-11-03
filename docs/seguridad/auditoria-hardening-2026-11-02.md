# Auditoría de hardening: broker MQTT y backend (2026-11-02)

**Fecha de la auditoría:** 2026-11-02, 18:54 (-03:00)
**Modo:** solo lectura, sin cambios en VPS ni en repos
**Host:** VPS DataMaq, AlmaLinux 8.10, kernel 4.18.0-553.180.1.el8_10.x86_64
**Ejecutada por:** sesión DevOps del VPS (acceso local), a pedido del dueño
**Motivo:** ola de ataques a controladores de refrigeración en Europa (oct–nov 2026)
**Plan de remediación:** [`plan-migracion-credenciales-mqtt.md`](plan-migracion-credenciales-mqtt.md)

---

## 1. Contexto: qué pasó y por qué importa

- **Francia, 11 oct 2026:** atacantes manipularon controladores de refrigeración de hasta 700 supermercados y los pasaron a descongelamiento nocturno. Muchas unidades llegaron a 50 °C. Los equipos mencionados son reguladores Danfoss AK-SM800 y AK-SC355 ([Wikipedia](https://en.wikipedia.org/wiki/2026_French_supermarket_refrigerator_hack), [CNBC](https://www.cnbc.com/2026/10/13/france-supermarket-hack-cyberattack-fridges-fires.html), [Schneier](https://www.schneier.com/blog/archives/2026/10/cyberattack-on-connected-fridges-in-france.html)).
- **2 nov 2026:** segunda oleada en Bélgica, Suecia, Luxemburgo, Países Bajos, Irlanda, Estonia y Finlandia ([El Ciudadano](https://elciudadanoweb.com/hackeo-en-la-cadena-de-frio-ciberataque-masivo-a-supermercados-en-europa-altero-las-heladeras-y-destruyo-toneladas-de-comida/), [ABC News](https://abcnews.com/International/european-grocery-chains-freezers-refrigerators-targeted-apparent-cyberattacks/story?id=137769974)).
- **Vector técnico (verificado por CISA y Claroty):** bypass de autenticación y ejecución remota de código en la interfaz web del AK-SM 800A, corregido en firmware R4.3.1 ([CISA ICSA-25-140-03](https://www.cisa.gov/news-events/ics-advisories/icsa-25-140-03), [Claroty Team82](https://claroty.com/team82/research/freeze-the-controller-defrost-the-food-uncovering-vulnerabilities-in-danfoss-refrigeration-controllers)). El AK-SM 800 está fuera de soporte desde mayo de 2021. Censys registró unos 2.765 equipos expuestos.

**Correcciones al planteo inicial:**
- No son heladeras domésticas. Son controladores comerciales de refrigeración.
- Las fuentes no hablan de una botnet. Las cifras varían entre medios (50 vs 70 °C; "hasta 700" vs "cientos").
- Las afirmaciones sobre módems celulares de mantenimiento y credenciales débiles aparecen en fuentes secundarias. No se confirmaron.

**Por qué nos alcanza, en la parte que aplica:** un medidor o controlador que acepta comandos remotos con una credencial compartida y sin ACL tiene el mismo patrón de riesgo: quien obtiene una credencial de campo obtiene la flota.

## 2. Hallazgos

| # | Área | Hallazgo | Estado |
|---|------|----------|--------|
| 1 | MQTT / ACL | El usuario `datamaq_device` tiene `topic readwrite #` en `/etc/mosquitto/acl`: lectura y escritura sobre todo el broker. | **ROJO** |
| 2 | MQTT / Autenticación | Una sola credencial (`datamaq_device`) para toda la flota de medidores y para el backend (`MQTT_USERNAME` en `.env`). Sin trazabilidad ni revocación individual. | **ROJO** |
| 3 | Red / Firewall | `table inet fwmin` con `policy accept` en `input`. Puertos de paneles de hosting (10000, 2082–2097) y de correo (25, 110, 143, 465, 587, 993, 995, 4190) escuchan en `0.0.0.0` y `[::]` sin filtrado. | AMARILLO |
| 4 | MQTT / Config | `require_certificate false`: autenticación solo por usuario y contraseña sobre TLS. | AMARILLO |
| 5 | Sistema / Parches | 7 paquetes de seguridad pendientes para el kernel (`kernel-4.18.0-553.182.1.el8_10`). | AMARILLO |
| 6 | Usuarios del broker | En `/etc/mosquitto/passwd` hay 3 usuarios: `datamaq_device`, `datamaq-telemetry-dev` y `datamaq-api-dev-ro`. Los usuarios `-dev` **no aparecen en ningún archivo del repo** `datamaq-telemetry`. No se sabe si los usa el staging. | **Por verificar** |
| 7 | MQTT / Red | Listener 1883 solo en `127.0.0.1`. Listener 8883 público con TLS. | VERDE |
| 8 | MQTT / Acceso | `allow_anonymous false`. | VERDE |
| 9 | MQTT / TLS | Certificado Let's Encrypt para `mqtt.datamaq.com.ar`, vence el 15 de enero de 2027 (73 días). | VERDE |
| 10 | Backend | Servicio `datamaq-telemetry.service` corre con usuario sin privilegios. Uvicorn en `127.0.0.1:8885` y `8886`, detrás de Nginx y HAProxy. | VERDE |
| 11 | Backend / Config | `.env` con permisos `640 datamaq datamaq-telemetry`. `MQTT_TLS_ENABLED=True`. | VERDE |
| 12 | SSH | `permitrootlogin without-password`, `passwordauthentication no`, fail2ban activo, 0 intentos fallidos en 24 h. | VERDE |

### 2.1 Detalle de los ROJOS

**H1: ACL global.** Un equipo con la credencial (o un atacante que la extraiga de un medidor en campo) puede suscribirse a toda la telemetría de todos los clientes y publicar en cualquier tópico, incluidos setpoints o comandos de relé. Remediación: ACL por dispositivo con `pattern` (`pattern readwrite devices/%u/#` o similar, a confirmar con el contrato de tópicos real) y un usuario de backend con permiso de lectura amplia pero sin escritura a los tópicos de dispositivos.

**H2: credencial compartida.** La documentación del repo lo confirma:
- `docs/provisioning_guide.md:35` lista el usuario MQTT como `datamaq_device`.
- `docs/provisioning_guide.md:63` pide exportar `MQTT_PASSWORD` con la contraseña de `datamaq_device` para aprovisionar cada medidor en campo.
- `docs/troubleshooting-conectividad-dispositivos.md:19` dice: "único usuario: `datamaq_device`".
- `profiles/datamaq_server.json:10` tiene el mismo usuario.

Como la contraseña ya está en cada medidor en campo, **rotarla sin reaprovisionar corta la ingesta**. La migración tiene que ser por etapas (ver plan).

### 2.2 Hallazgo H6: usuarios `-dev` en el broker de producción

`datamaq-telemetry-dev` y `datamaq-api-dev-ro` existen en el broker de producción. El repo no los menciona. Antes de tocarlos hay que confirmar:
- Si el staging (`.github/workflows/deploy-staging.yml`, que apunta a `/var/www/datamaq-telemetry-dev`) usa alguno de los dos.
- Qué permisos tienen en `/etc/mosquitto/acl`. El reporte no lo dice.

## 3. Lo que no se verificó

1. **`ufw`:** no está instalado. Se usó `nft list ruleset` en su lugar.
2. **`apt` y `unattended-upgrades`:** son de Debian/Ubuntu. Se usó `dnf check-update --security` y `dnf-automatic.timer` (habilitado).
3. **Tráfico en vivo del broker:** no se suscribió a tópicos ni se inspeccionó red, por ser una auditoría pasiva.
4. **Contenido de `/etc/mosquitto/acl`** para los usuarios `-dev`: pendiente.
5. **Configuración de Nginx y HAProxy:** no se revisó.
6. **Firmware de los medidores:** no se verificó si soporta mTLS ni si admite cambio remoto de credenciales.

## 4. Confirmación

La auditoría fue de solo lectura. No se modificó configuración, código ni archivos del VPS. No se reiniciaron servicios, no se instalaron paquetes y no se ejecutó `git pull`. No se imprimieron valores de contraseñas ni contenido de `.env`.

## 5. Fuentes

- [Wikipedia: 2026 French supermarket refrigerator hack](https://en.wikipedia.org/wiki/2026_French_supermarket_refrigerator_hack)
- [SecurityWeek: Refrigeration Controller Hack Spoils Food Across European Supermarkets](https://www.securityweek.com/refrigeration-controller-hack-spoils-food-across-european-supermarkets/)
- [CNBC: French supermarket fridges get hacked](https://www.cnbc.com/2026/10/13/france-supermarket-hack-cyberattack-fridges-fires.html)
- [Schneier on Security: Cyberattack on Connected Fridges in France](https://www.schneier.com/blog/archives/2026/10/cyberattack-on-connected-fridges-in-france.html)
- [El Ciudadano: Hackeo en la cadena de frío](https://elciudadanoweb.com/hackeo-en-la-cadena-de-frio-ciberataque-masivo-a-supermercados-en-europa-altero-las-heladeras-y-destruyo-toneladas-de-comida/)
- [ABC News: European grocery chains' freezers targeted](https://abcnews.com/International/european-grocery-chains-freezers-refrigerators-targeted-apparent-cyberattacks/story?id=137769974)
- [CISA ICSA-25-140-03: Danfoss AK-SM 8xxA Series](https://www.cisa.gov/news-events/ics-advisories/icsa-25-140-03)
- [Claroty Team82: Freeze the controller, defrost the food](https://claroty.com/team82/research/freeze-the-controller-defrost-the-food-uncovering-vulnerabilities-in-danfoss-refrigeration-controllers)
- [Water ISAC: CISA urges manufacturers to eliminate default passwords](https://www.waterisac.org/cisa-urges-manufacturers-eliminate-default-passwords-thwart-cyber-threats)
