#!/usr/bin/env python3
"""Descubre dispositivos Tuya (Smart Life) en la red local.

Uso:
    python scripts/discover_tuya_devices.py

Requisitos:
    pip install tinytuya
"""

import socket
import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor
import sys


def get_local_network() -> str | None:
    """Obtiene el rango de IP de la red local."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        # Asume /24 (típico en redes hogareñas)
        return ip.rsplit(".", 1)[0] + ".0/24"
    except Exception as e:
        print(f"❌ Error obteniendo red local: {e}", file=sys.stderr)
        return None


def scan_port(ip: str, port: int = 6668, timeout: float = 0.5) -> bool:
    """Intenta conectar a puerto (típico de Tuya en LAN)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def reverse_dns(ip: str) -> str | None:
    """Intenta resolver hostname."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def main() -> None:
    """Escanea la red y descubre dispositivos."""
    network = get_local_network()
    if not network:
        print("❌ No se pudo detectar tu red local.", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Escaneando red: {network}")
    print("⏳ Esto puede tardar 30-60 segundos...\n")

    activos: list[tuple[str, str]] = []

    def probar_ip(ip_str: str) -> None:
        if scan_port(ip_str):
            hostname = reverse_dns(ip_str)
            activos.append((ip_str, hostname or "desconocido"))
            print(f"  ✓ {ip_str:<15} ({hostname or 'desconocido'})")

    # Escanea todas las IPs en la red con paralelismo
    ips = ipaddress.ip_network(network, strict=False)
    with ThreadPoolExecutor(max_workers=50) as executor:
        for ip in ips:
            executor.submit(probar_ip, str(ip))

    print(f"\n✅ Encontrados {len(activos)} dispositivos activos:")
    for ip, hostname in sorted(activos):
        print(f"  • {ip:<15} {hostname}")

    # Intenta descubrimiento Tuya (más preciso)
    print("\n🔌 Intentando descubrimiento Tuya...")
    try:
        import tinytuya  # type: ignore

        print("  ⏳ Esperando broadcasts de dispositivos Tuya...")
        print("     (Puede tomar 10-20 segundos)")

        devices = tinytuya.deviceScan(verbose=False)

        if devices and len(devices) > 0:
            print(f"\n  ✅ Dispositivos Tuya encontrados:\n")
            for dev_id, info in sorted(devices.items()):
                print(f"    📦 Dispositivo: {info.get('name', 'Desconocido')}")
                print(f"       Device ID:  {dev_id}")
                print(f"       IP:         {info.get('ip', 'N/A')}")
                print(f"       Versión:    {info.get('version', 'N/A')}")
                print(f"       Puerto:     {info.get('port', 'N/A')}")
                print()
        else:
            print("  ⚠️  No se encontraron dispositivos Tuya por broadcast.")
            print("     Esto puede ocurrir si:")
            print("     • El dispositivo NO está encendido")
            print("     • NO está conectado a la misma WiFi que esta laptop")
            print("     • La app Smart Life aún no terminó el emparejamiento")
            print("     • Tu router NO permite UDP broadcasts entre subredes")
            print("     • El GF-SMBOX no está basado en Tuya (fallback a manual)")

    except ImportError:
        print("  ⚠️  'tinytuya' no está instalado.")
        print("     Instala con: pip install tinytuya")
    except Exception as e:
        print(f"  ❌ Error en descubrimiento Tuya: {e}")


if __name__ == "__main__":
    main()
