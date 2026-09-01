#!/usr/bin/env python3
"""
Herramienta de Aprovisionamiento de Medidores Powermeter para Datamaq
Permite alternar entre el servidor de Datamaq Telemetry y el servidor oficial de Powermeter.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request


def make_request(url, method="GET", data=None, user="admin", password="powermeter"):
    auth_str = base64.b64encode(f"{user}:{password}".encode()).decode("utf-8")
    headers = {
        "Authorization": f"Basic {auth_str}",
        "User-Agent": "Datamaq-Provision-Tool/1.0",
        "Accept": "application/json",
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            try:
                return resp.status, json.loads(content)
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        return e.code, err_body
    except Exception as e:
        return 0, str(e)


def show_status(host, user, password):
    print(f"[*] Consultando estado de Powermeter en http://{host}/ ...")
    status_code, info = make_request(f"http://{host}/status.json", user=user, password=password)
    if status_code != 200:
        print(f"[!] Error al consultar estado (HTTP {status_code}): {info}")
        return

    dev = info.get("device_info", {})
    mqtt = info.get("mqtt", {})
    wifi = info.get("wifi_sta", {})

    print("\n" + "=" * 55)
    print("           ESTADO ACTUAL DEL MEDIDOR")
    print("=" * 55)
    print(f"• Dispositivo:      {dev.get('device_name')} (S/N: {dev.get('serial_number')})")
    print(f"• Modelo:           {dev.get('device_model')} - Hardware: {dev.get('hw_model')}")
    print(f"• Firmware:         {dev.get('device_fw')}")
    print(f"• MAC / Client ID:  {wifi.get('mac')}")
    print(f"• Wi-Fi STA:        Conectado={wifi.get('connected')} | IP={wifi.get('ip')} | Señal={wifi.get('quality')}%")
    print(
        f"• Broker MQTT:      {mqtt.get('broker_host')}:{mqtt.get('broker_port')} (Conectado={mqtt.get('connected')})"
    )
    print("=" * 55)
    _diagnosticar(wifi, mqtt)
    print()


def _diagnosticar(wifi, mqtt):
    """Traduce el status.json a un veredicto: ¿falló el Wi-Fi o falló el broker?"""
    wifi_ok = bool(wifi.get("connected"))
    mqtt_ok = bool(mqtt.get("connected"))

    if not wifi_ok:
        print("[!] DIAGNÓSTICO: el equipo NO está asociado a la red Wi-Fi.")
        print("    El fallo es de red local, no del servidor. Revisar SSID/clave y que")
        print("    la red sea 2.4 GHz WPA2 (el ESP32 no soporta 5 GHz ni WPA3-only).")
        return

    calidad = wifi.get("quality")
    if isinstance(calidad, (int, float)) and calidad < 40:
        print(f"[!] ADVERTENCIA: señal Wi-Fi baja ({calidad}%). Esperables cortes por keepalive.")

    if not mqtt_ok:
        print("[!] DIAGNÓSTICO: Wi-Fi OK pero el broker MQTT rechaza o no responde.")
        print(f"    IP asignada: {wifi.get('ip')} | Broker: {mqtt.get('broker_host')}:{mqtt.get('broker_port')}")
        print("    Verificar puerto 8883 + TLS-SERVER-AUTH + usuario/contraseña + certificado CA.")
        print("    Contrastar con el log del broker: ./scripts/logs.sh --mqtt --device")
        return

    print("[✓] DIAGNÓSTICO: Wi-Fi y MQTT conectados. El equipo está reportando.")


def _validar_config(mqtt_cfg, ca_cert):
    """Rechaza combinaciones que el broker de Datamaq no puede aceptar.

    El broker (`/etc/mosquitto/conf.d/datamaq.conf`) tiene `allow_anonymous false` y
    expone el 1883 solo en loopback: un perfil sin credenciales, o apuntando al 1883,
    deja al medidor sin poder conectar nunca.
    """
    errores = []
    puerto = int(mqtt_cfg.get("broker_port") or 0)
    seguridad = (mqtt_cfg.get("security") or "").upper()
    usuario = mqtt_cfg.get("username") or ""
    clave = mqtt_cfg.get("password") or ""
    host = mqtt_cfg.get("broker_host") or ""

    if puerto == 1883 and host not in ("127.0.0.1", "localhost"):
        errores.append(
            "Puerto 1883: el broker solo lo escucha en 127.0.0.1. Desde el medidor usar 8883 con TLS-SERVER-AUTH."
        )

    if seguridad == "NO-SECURITY" and puerto == 8883:
        errores.append("El puerto 8883 exige TLS: usar --security TLS-SERVER-AUTH.")

    if not usuario or not clave:
        errores.append(
            "Faltan credenciales MQTT (el broker no acepta anónimos). "
            "Pasar --mqtt-username/--mqtt-password o exportar MQTT_PASSWORD."
        )

    if seguridad.startswith("TLS") and not ca_cert:
        errores.append("Modo TLS sin certificado CA: el equipo no podrá validar al broker.")

    if errores:
        print("[!] Configuración inválida, no se envía nada al equipo:")
        for e in errores:
            print(f"    - {e}")
        return False

    return True


def apply_profile(
    host,
    profile_name,
    custom_host=None,
    custom_port=None,
    custom_security=None,
    custom_username=None,
    custom_password=None,
    custom_ca_file=None,
    user="admin",
    password="powermeter",
    reboot=False,
):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))

    if profile_name == "datamaq":
        profile_file = os.path.join(project_root, "profiles", "datamaq_server.json")
    elif profile_name in ("powermeter-official", "powermeter_official", "official"):
        profile_file = os.path.join(project_root, "profiles", "powermeter_official.json")
    else:
        profile_file = profile_name

    if not os.path.exists(profile_file):
        print(f"[!] Archivo de perfil no encontrado: {profile_file}")
        sys.exit(1)

    with open(profile_file, encoding="utf-8") as f:
        profile = json.load(f)

    mqtt_cfg = profile.get("mqtt_config", {})
    ca_cert = profile.get("mqtt_ca_certificate", "")

    # CA embebida por referencia: el perfil apunta a un PEM del repo en vez de inlinearlo.
    ca_ref = profile.get("mqtt_ca_certificate_file")
    if not ca_cert and ca_ref:
        ca_path = ca_ref if os.path.isabs(ca_ref) else os.path.join(project_root, ca_ref)
        if os.path.exists(ca_path):
            with open(ca_path, encoding="utf-8") as f:
                ca_cert = f.read().strip()
        else:
            print(f"[!] El perfil referencia un CA inexistente: {ca_path}")
            sys.exit(1)

    # Sobrescribir con argumentos CLI si se proveyeron
    if custom_host:
        mqtt_cfg["broker_host"] = custom_host
    if custom_port:
        mqtt_cfg["broker_port"] = int(custom_port)
    if custom_security:
        mqtt_cfg["security"] = custom_security
    if custom_username:
        mqtt_cfg["username"] = custom_username
    if custom_password:
        mqtt_cfg["password"] = custom_password
    if custom_ca_file:
        with open(custom_ca_file, encoding="utf-8") as f:
            ca_cert = f.read().strip()

    if not _validar_config(mqtt_cfg, ca_cert):
        sys.exit(1)

    print(f"[*] Aplicando perfil '{profile.get('_description', profile_name)}' a http://{host}/ ...")
    print(f"    - Broker Host: {mqtt_cfg.get('broker_host')}")
    print(f"    - Broker Port: {mqtt_cfg.get('broker_port')}")
    print(f"    - Seguridad:   {mqtt_cfg.get('security')}")
    print(f"    - Usuario:     {mqtt_cfg.get('username') or '(anónimo)'}")
    print(f"    - CA TLS:      {'incluida' if ca_cert else '(ninguna)'}")

    # 1. Enviar configuración MQTT
    code, res = make_request(
        f"http://{host}/mqtt_config.json", method="POST", data=mqtt_cfg, user=user, password=password
    )
    if code not in (200, 204):
        print(f"[!] Error al enviar mqtt_config.json (HTTP {code}): {res}")
        return False
    print("  [+] Configuración MQTT actualizada.")

    # 2. Enviar Certificado CA (solo si tenemos uno: un POST vacío BORRA el CA del equipo)
    if ca_cert:
        ca_payload = {"ca_certificate": ca_cert}
        code_ca, res_ca = make_request(
            f"http://{host}/mqtt_ca_certificate_config.json",
            method="POST",
            data=ca_payload,
            user=user,
            password=password,
        )
        if code_ca in (200, 204):
            print("  [+] Certificado CA MQTT actualizado.")
        else:
            print(f"[!] Error al enviar el certificado CA (HTTP {code_ca}): {res_ca}")
            return False
    else:
        print("  [i] Sin certificado CA en el perfil: se conserva el que ya tiene el equipo.")

    print("\n[✓] ¡Perfil aplicado correctamente!")

    if reboot:
        print("[*] Reiniciando equipo para aplicar cambios...")
        make_request(f"http://{host}/reboot.json", method="POST", data={}, user=user, password=password)
        print("[✓] Petición de reinicio enviada.")
    else:
        print("[i] Sugerencia: reinicia el equipo desde la web o con --reboot para asegurar la conexión inmediata.")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aprovisionamiento de Servidor en Powermeter (Datamaq vs Oficial)")
    parser.add_argument("--host", default="192.168.4.1", help="IP del Powermeter (default: 192.168.4.1)")
    parser.add_argument("--user", default="admin", help="Usuario HTTP Basic Auth (default: admin)")
    parser.add_argument("--password", default="powermeter", help="Contraseña HTTP Basic Auth (default: powermeter)")
    parser.add_argument("--status", action="store_true", help="Mostrar estado y broker actual del medidor")
    parser.add_argument("--profile", choices=["datamaq", "powermeter-official"], help="Perfil a aplicar")
    parser.add_argument("--broker-host", help="Sobrescribir Host del Broker (ej: IP o dominio de tu VPS)")
    parser.add_argument("--broker-port", type=int, help="Sobrescribir Puerto del Broker (ej: 1883 o 8883)")
    parser.add_argument("--security", help="Sobrescribir modo de seguridad (NO-SECURITY o TLS-SERVER-AUTH)")
    parser.add_argument("--mqtt-username", help="Usuario MQTT a enviar al medidor (sobrescribe el perfil)")
    parser.add_argument(
        "--mqtt-password",
        default=os.environ.get("MQTT_PASSWORD"),
        help="Contraseña MQTT a enviar al medidor (default: variable de entorno MQTT_PASSWORD)",
    )
    parser.add_argument("--mqtt-ca-file", help="Archivo PEM del certificado CA (raíz) para TLS-SERVER-AUTH")
    parser.add_argument("--reboot", action="store_true", help="Reiniciar el equipo tras aplicar la configuración")

    args = parser.parse_args()

    if args.status:
        show_status(args.host, args.user, args.password)
    elif args.profile:
        ok = apply_profile(
            host=args.host,
            profile_name=args.profile,
            custom_host=args.broker_host,
            custom_port=args.broker_port,
            custom_security=args.security,
            custom_username=args.mqtt_username,
            custom_password=args.mqtt_password,
            custom_ca_file=args.mqtt_ca_file,
            user=args.user,
            password=args.password,
            reboot=args.reboot,
        )
        sys.exit(0 if ok else 1)
    else:
        show_status(args.host, args.user, args.password)
