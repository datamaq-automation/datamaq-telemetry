#!/usr/bin/env python3
"""
Script de Backup para Medidores de Energía Powermeter (ESP32)
Descarga y respalda todos los endpoints de configuración, certificados y estado.
"""

import argparse
import base64
import datetime
import gzip
import json
import os
import urllib.error
import urllib.request

DEFAULT_ENDPOINTS = [
    "home.html",
    "style.css",
    "alpinejs.js",
    "PowermeterMIB.mib",
    "admin_config.json",
    "calibration_const_config.json",
    "device_config.json",
    "device_info.json",
    "event_config.json",
    "harmonics.json",
    "lan_config.json",
    "mdns_config.json",
    "measurements.json",
    "modbus_server_config.json",
    "mqtt_ca_certificate_config.json",
    "mqtt_config.json",
    "mqtt_device_certificate_config.json",
    "mqtt_device_private_key_config.json",
    "mqtt_topics_config.json",
    "ntp_config.json",
    "selfcheck.json",
    "snmp_config.json",
    "speedwire_config.json",
    "ssdp_config.json",
    "status.json",
    "wifiscan.json",
]


def backup_device(host="192.168.4.1", user="admin", password="powermeter", output_base="backups"):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(output_base, f"powermeter_{timestamp}")
    latest_dir = os.path.join(output_base, "latest")
    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(latest_dir, exist_ok=True)

    auth_str = base64.b64encode(f"{user}:{password}".encode()).decode("utf-8")
    headers = {
        "Authorization": f"Basic {auth_str}",
        "User-Agent": "Datamaq-Backup-Tool/1.0",
        "Accept-Encoding": "gzip, deflate",
    }

    print(f"[*] Iniciando backup de Powermeter en http://{host}/")
    print(f"[*] Directorio de destino: {backup_dir}")

    summary = {}
    downloaded_files = 0
    failed_files = 0

    for ep in DEFAULT_ENDPOINTS:
        url = f"http://{host}/{ep.lstrip('/')}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                if resp.info().get("Content-Encoding") == "gzip" or data.startswith(b"\x1f\x8b"):
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass

                filename = ep.lstrip("/").replace("/", "_")
                dest_file = os.path.join(backup_dir, filename)
                latest_file = os.path.join(latest_dir, filename)

                with open(dest_file, "wb") as f:
                    f.write(data)
                with open(latest_file, "wb") as f:
                    f.write(data)

                print(f"  [+] {ep:<35} OK ({len(data):>7} bytes)")
                downloaded_files += 1

                if filename.endswith(".json"):
                    try:
                        summary[ep] = json.loads(data.decode("utf-8"))
                    except Exception:
                        summary[ep] = data.decode("utf-8", errors="ignore")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  [-] {ep:<35} NO DISPONIBLE (HTTP 404)")
            else:
                print(f"  [!] {ep:<35} ERROR HTTP {e.code}")
            failed_files += 1
        except Exception as e:
            print(f"  [!] {ep:<35} ERROR: {e}")
            failed_files += 1

    # Guardar resumen consolidado en JSON
    consolidated_path = os.path.join(backup_dir, "consolidated_backup.json")
    consolidated_latest = os.path.join(latest_dir, "consolidated_backup.json")

    with open(consolidated_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(consolidated_latest, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 50)
    print("[✓] Backup completado exitosamente.")
    print(f"    - Archivos descargados: {downloaded_files}")
    print(f"    - Archivos no encontrados/fallidos: {failed_files}")
    print(f"    - Copia versionada: {backup_dir}")
    print(f"    - Acceso rápido: {latest_dir}")
    print(f"    - JSON consolidado: {consolidated_path}")
    print("=" * 50)

    # Mostrar datos clave respaldados
    dev_info = summary.get("device_info.json", {})
    mqtt_info = summary.get("mqtt_config.json", {})
    lan_info = summary.get("lan_config.json", {})
    if dev_info:
        print("\n--- RESUMEN DEL DISPOSITIVO RESPALDADO ---")
        print(f"• Número de Serie: {dev_info.get('serial_number')}")
        print(f"• Nombre del Equipo: {dev_info.get('device_name')}")
        print(f"• Modelo Hardware: {dev_info.get('hw_model')} (Firmware {dev_info.get('device_fw')})")
        print(f"• Broker MQTT Anterior: {mqtt_info.get('broker_host')}:{mqtt_info.get('broker_port')}")
        print(f"• Client ID / MAC: {mqtt_info.get('client_id')}")
        wifi_sta = lan_info.get("wifi_sta", [{}])[0] if isinstance(lan_info.get("wifi_sta"), list) else {}
        print(f"• Red Wi-Fi STA Guardada: SSID='{wifi_sta.get('ssid')}', Password='{wifi_sta.get('password')}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup de configuración de Powermeter ESP32")
    parser.add_argument("--host", default="192.168.4.1", help="IP del Powermeter (default: 192.168.4.1)")
    parser.add_argument("--user", default="admin", help="Usuario HTTP Basic Auth (default: admin)")
    parser.add_argument("--password", default="powermeter", help="Contraseña HTTP Basic Auth (default: powermeter)")
    parser.add_argument("--out", default="backups", help="Directorio base para guardar backups (default: backups)")

    args = parser.parse_args()
    backup_device(host=args.host, user=args.user, password=args.password, output_base=args.out)
