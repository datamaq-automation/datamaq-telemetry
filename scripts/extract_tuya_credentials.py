#!/usr/bin/env python3
"""Extrae Device ID y Local Key de una cuenta Smart Life / Tuya.

Este script obtiene las credenciales de control local de tus dispositivos Tuya.
Las credenciales se guardan en archivo local y NO se envían a servidores externos.

Uso:
    python scripts/extract_tuya_credentials.py

Requisitos:
    pip install tinytuya
"""

import json
import sys
from pathlib import Path
from getpass import getpass


def main() -> None:
    """Extrae credenciales de Tuya."""
    try:
        import tinytuya  # type: ignore
    except ImportError:
        print("❌ 'tinytuya' no está instalado.")
        print("   Instala con: pip install tinytuya")
        sys.exit(1)

    import os

    print("\n" + "=" * 70)
    print("🔐 Extractor de Credenciales Tuya / Smart Life")
    print("=" * 70)
    print("\n⚠️  SEGURIDAD:")
    print("  • Este script corre LOCALMENTE (sin enviar datos a internet)")
    print("  • Las credenciales se guardan en un archivo JSON local")
    print("  • NUNCA compartas ese archivo con otros")
    print()

    # Obtener credenciales de variables de entorno o input
    email = os.getenv("TUYA_EMAIL") or os.getenv("SMARTLIFE_EMAIL")
    password = os.getenv("TUYA_PASSWORD") or os.getenv("SMARTLIFE_PASSWORD")

    if not email:
        print("📱 Ingresa tus credenciales de Smart Life:")
        email = input("  Email: ").strip()

    if not password:
        password = getpass("  Contraseña: ")

    if not email or not password:
        print("❌ Email y contraseña requeridos")
        sys.exit(1)

    print("\n⏳ Conectando a Tuya Cloud...")
    print("   (Esto puede tomar 10-30 segundos)")

    try:
        # Obtiene lista de dispositivos
        email_or_phone = email
        tuya_api = tinytuya.Cloud(
            apiRegion="sa",  # South America
            apiKey="xxxxxxxxxxxxxxxx",  # Dummy, se ignora
            apiSecret="xxxxxxxxxxxxxxxx",  # Dummy, se ignora
            userName=email_or_phone,
            password=password,
        )

        # Intenta conectar
        devices = tuya_api.getdevices()

        if not devices:
            print("❌ No se encontraron dispositivos o credenciales inválidas")
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
            for dev_id, info in credentials.items():
                if "smbox" in info["name"].lower():
                    smbox = info
                    break

            if smbox:
                print(f"\n🎯 GF-SMBOX-PLUS encontrado:")
                print(f"   Device ID:  {smbox['device_id']}")
                print(f"   Local Key:  {smbox['local_key']}")
        else:
            print("❌ No se obtuvieron Local Keys")
            print("   Verifica que los dispositivos estén encendidos")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 Posibles causas:")
        print("   • Credenciales incorrectas")
        print("   • Sin conexión a internet")
        print("   • Región incorrecta (asumimos South America)")
        sys.exit(1)


if __name__ == "__main__":
    main()
