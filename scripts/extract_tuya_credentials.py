#!/usr/bin/env python3
"""Extrae Device ID y Local Key de una cuenta Smart Life / Tuya.

Este script obtiene las credenciales de control local de tus dispositivos Tuya
usando la API Cloud oficial de Tuya IoT Platform (https://iot.tuya.com).
Las credenciales se guardan en archivo local y NO se envían a servidores externos.

Requiere un proyecto Cloud en Tuya IoT Platform (Access ID + Access Secret) con
la cuenta Smart Life vinculada vía "Link Tuya App Account" (QR). El login directo
con usuario/contraseña de Smart Life está deprecado por Tuya (clientId inválido).

Uso:
    python scripts/extract_tuya_credentials.py

Variables de entorno (.env):
    TUYA_API_REGION      Región del proyecto Cloud (default: sa)
    TUYA_ACCESS_ID       Access ID / Client ID del proyecto Cloud
    TUYA_ACCESS_SECRET   Access Secret del proyecto Cloud

Requisitos:
    pip install tinytuya python-dotenv
"""

import json
import sys
from getpass import getpass
from pathlib import Path


def main() -> None:
    """Extrae credenciales de Tuya."""
    try:
        import tinytuya  # type: ignore
    except ImportError:
        print("❌ 'tinytuya' no está instalado.")
        print("   Instala con: pip install tinytuya")
        sys.exit(1)

    import os

    from dotenv import load_dotenv

    load_dotenv()

    print("\n" + "=" * 70)
    print("🔐 Extractor de Credenciales Tuya / Smart Life")
    print("=" * 70)
    print("\n⚠️  SEGURIDAD:")
    print("  • Este script corre LOCALMENTE (sin enviar datos a internet)")
    print("  • Las credenciales se guardan en un archivo JSON local")
    print("  • NUNCA compartas ese archivo con otros")
    print()

    # Credenciales del proyecto Cloud de Tuya IoT Platform (obligatorias)
    region = os.getenv("TUYA_API_REGION", "sa")
    access_id = os.getenv("TUYA_ACCESS_ID")
    access_secret = os.getenv("TUYA_ACCESS_SECRET")

    if not access_id:
        access_id = input("  Access ID (Client ID) del proyecto Cloud: ").strip()

    if not access_secret:
        access_secret = getpass("  Access Secret del proyecto Cloud: ")

    if not access_id or not access_secret:
        print("❌ Access ID y Access Secret requeridos")
        print("   Crear un proyecto en https://iot.tuya.com y vincular la app")
        print("   Smart Life vía 'Link Tuya App Account' (QR)")
        sys.exit(1)

    print("\n⏳ Conectando a Tuya Cloud...")
    print("   (Esto puede tomar 10-30 segundos)")

    try:
        tuya_api = tinytuya.Cloud(
            apiRegion=region,
            apiKey=access_id,
            apiSecret=access_secret,
        )

        # Intenta conectar
        devices = tuya_api.getdevices()

        if not devices:
            print("❌ No se encontraron dispositivos")
            print("   Verifica que la cuenta Smart Life esté vinculada al proyecto")
            print("   Cloud vía 'Link Tuya App Account'")
            sys.exit(1)

        print(f"\n✅ Encontrados {len(devices)} dispositivo(s):\n")

        # Filtra dispositivos WiFi (especialmente switches)
        wifi_devices = []
        for device in devices:
            device_type = device.get("category", "UNKNOWN")
            device_name = device.get("name", "Desconocido")
            device_id = device.get("id", "")

            print(f"  📦 {device_name}")
            print(f"     ID: {device_id}")
            print(f"     Tipo: {device_type}")
            print()

            # Busca el GF-SMBOX
            if "smbox" in device_name.lower() or "gralf" in device_name.lower():
                wifi_devices.append(device)

        if not wifi_devices:
            print("⚠️  No se encontró GF-SMBOX específicamente.")
            print("   Cualquiera de los dispositivos arriba podría ser el tuyo.")
            return

        # Ahora obtiene local keys
        print("\n🔑 Extrayendo Local Keys...")
        print("   (Requiere que los dispositivos estén encendidos y en red)")

        output_file = Path("tuya_devices_credentials.json")

        credentials = {}
        for device in devices:
            device_id = device.get("id")
            device_name = device.get("name", "Unknown")

            try:
                # Obtiene el local key del dispositivo
                local_key = tuya_api.getlocalkeybyid(device_id)

                if local_key:
                    credentials[device_id] = {
                        "name": device_name,
                        "device_id": device_id,
                        "local_key": local_key,
                        "category": device.get("category"),
                    }
                    print(f"  ✓ {device_name:<30} Local Key: {local_key[:16]}...")
            except Exception as e:
                print(f"  ❌ {device_name:<30} Error: {e}")

        if credentials:
            # Guarda en archivo
            with open(output_file, "w") as f:
                json.dump(credentials, f, indent=2)

            print(f"\n✅ Credenciales guardadas en: {output_file}")
            print("\n📋 Contenido (MANTÉN ESTO SEGURO):")
            print(json.dumps(credentials, indent=2))

            # Busca el SMBOX específicamente
            smbox = None
            for info in credentials.values():
                if "smbox" in info["name"].lower():
                    smbox = info
                    break

            if smbox:
                print("\n🎯 GF-SMBOX-PLUS encontrado:")
                print(f"   Device ID:  {smbox['device_id']}")
                print(f"   Local Key:  {smbox['local_key']}")
        else:
            print("❌ No se obtuvieron Local Keys")
            print("   Verifica que los dispositivos estén encendidos")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 Posibles causas:")
        print("   • Access ID / Access Secret incorrectos")
        print("   • Cuenta Smart Life no vinculada al proyecto Cloud")
        print("   • Sin conexión a internet")
        print(f"   • Región incorrecta (usando: {region})")
        sys.exit(1)


if __name__ == "__main__":
    main()
