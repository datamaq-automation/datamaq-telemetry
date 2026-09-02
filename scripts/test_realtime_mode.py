#!/usr/bin/env python3
"""
Herramienta de Diagnóstico y Activación de Tiempo Real para Medidores Powermeter.

Permite:
- Consultar la configuración de cadencia (/sync_rate_config.json)
- Activar temporalmente el modo de alta frecuencia (/realtime_sync_mode.json)
- Detener el modo de alta frecuencia (/realtime_sync_mode_stop.json)
- Medir la cadencia real (delta entre tramas) de publicaciones en m/wifi/{device_uid}/inst
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt no está instalado en el entorno.", file=sys.stderr)
    sys.exit(1)


def parsear_env(env_path: Path) -> dict[str, str]:
    valores = {}
    if not env_path.exists():
        return valores
    for linea in env_path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        valores[k.strip()] = v.strip().strip("'\"")
    return valores


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico de tiempo real y cadencia de medidores Powermeter")
    parser.add_argument(
        "--device-uid",
        "-d",
        default="D48C49F03564",
        help="UID o MAC del medidor (default: D48C49F03564)",
    )
    parser.add_argument(
        "--action",
        "-a",
        choices=["listen", "get_sync_rate", "start_realtime", "stop_realtime", "set_rate"],
        default="listen",
        help="Acción a realizar sobre el medidor (default: listen)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duración en segundos de la captura o modo tiempo real (default: 60)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=5,
        help="Período en segundos para set_rate (default: 5)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Broker MQTT host (default: lee de .env o 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Puerto MQTT (default: lee de .env o 1883/8883)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Usuario MQTT (default: lee de .env)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Contraseña MQTT (default: lee de .env)",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="Forzar conexión TLS",
    )
    parser.add_argument(
        "--ca-file",
        default=None,
        help="Ruta al certificado CA para TLS",
    )

    args = parser.parse_args()

    # Cargar variables de entorno si existen
    env_vars = {}
    for ruta in [Path(".env"), Path("/var/www/datamaq-telemetry/.env")]:
        if ruta.exists():
            env_vars = parsear_env(ruta)
            break

    host = args.host or env_vars.get("MQTT_BROKER_HOST", "127.0.0.1")
    port = args.port or (int(env_vars.get("MQTT_BROKER_PORT", 8883 if "datamaq.com.ar" in host else 1883)))
    username = args.username or env_vars.get("MQTT_USERNAME", "datamaq_device")
    password = args.password or env_vars.get("MQTT_PASSWORD", "")
    use_tls = args.tls or (env_vars.get("MQTT_TLS_ENABLED", "false").lower() == "true" or port == 8883)
    ca_file = args.ca_file or env_vars.get("MQTT_TLS_CA_CERTS")

    topic_inst = f"m/wifi/{args.device_uid}/inst"
    topic_rta = f"m/wifi/{args.device_uid}/conf/rta"
    topic_com = f"m/wifi/{args.device_uid}/conf/com"

    print("=" * 70)
    print("Datamaq Telemetry — Diagnóstico de Telemetría y Tiempo Real")
    print("=" * 70)
    print(f"Broker:    {host}:{port} (TLS: {use_tls})")
    print(f"Dispositivo: {args.device_uid}")
    print(f"Acción:    {args.action}")
    print(f"Duración:  {args.duration} s")
    print("-" * 70)

    mensajes_recibidos = []
    ultimo_ts = None

    def on_connect(client: Any, userdata: Any, flags: Any, rc: int, props: Any = None) -> None:
        if rc != 0:
            print(f"Error de conexión MQTT: rc={rc}", file=sys.stderr)
            return
        print("Conectado al broker. Suscribiendo a tópicos de telemetría y respuestas...")
        client.subscribe([(topic_inst, 1), (topic_rta, 1)])

        correlator = int(time.time())
        comando = None

        if args.action == "get_sync_rate":
            comando = {"correlatorid": correlator, "get": "/sync_rate_config.json"}
        elif args.action == "start_realtime":
            comando = {
                "correlatorid": correlator,
                "set": "/realtime_sync_mode.json",
                "payload": {"time_s": args.duration},
            }
        elif args.action == "stop_realtime":
            comando = {
                "correlatorid": correlator,
                "set": "/realtime_sync_mode_stop.json",
                "payload": {},
            }
        elif args.action == "set_rate":
            comando = {
                "correlatorid": correlator,
                "set": "/sync_rate_config.json",
                "payload": {"online_sr_inst": args.rate},
            }

        if comando:
            payload_str = json.dumps(comando)
            print(f"Publicando comando en {topic_com}:\n  {payload_str}")
            client.publish(topic_com, payload_str, qos=1)

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        nonlocal ultimo_ts
        ahora = time.time()
        hora_str = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        delta_str = f"+{ahora - ultimo_ts:.2f}s" if ultimo_ts else "inicial"
        ultimo_ts = ahora

        if msg.topic == topic_rta:
            print(f"\n[{hora_str} UTC] [RESPUESTA DISPOSITIVO] {topic_rta}:")
            try:
                data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
                print(f"  {json.dumps(data, indent=2)}")
            except Exception:
                print(f"  {msg.payload.decode('latin1', errors='ignore')}")
            return

        if msg.topic == topic_inst:
            try:
                data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
                potencias = []
                fases = data.get("f", [])
                for f in fases:
                    potencias.append(f"{f.get('n', '?')}: {f.get('p', 0):.1f}W")
                tot_str = f" | Potencias: {', '.join(potencias)}" if potencias else ""
                print(f"[{hora_str} UTC] [{delta_str}] Trama inst recibida (t={data.get('t')}){tot_str}")
                mensajes_recibidos.append((ahora, data))
            except Exception:
                print(f"[{hora_str} UTC] [{delta_str}] Trama cruda ({len(msg.payload)} bytes) en {msg.topic}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username:
        client.username_pw_set(username, password)
    if use_tls:
        if ca_file and Path(ca_file).exists():
            client.tls_set(ca_certs=ca_file)
        else:
            client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(host, port, 60)
    except Exception as e:
        print(f"Error conectando al broker {host}:{port}: {e}", file=sys.stderr)
        sys.exit(1)

    client.loop_start()
    print(f"Monitoreando durante {args.duration} segundos... (Presiona Ctrl+C para salir)\n")
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("\nInterrupción recibida.")
    finally:
        client.loop_stop()
        client.disconnect()

    print("\n" + "=" * 70)
    print("Resumen de Observación")
    print("=" * 70)
    print(f"Total tramas 'inst' recibidas: {len(mensajes_recibidos)}")
    if len(mensajes_recibidos) >= 2:
        deltas = [mensajes_recibidos[i][0] - mensajes_recibidos[i - 1][0] for i in range(1, len(mensajes_recibidos))]
        promedio = sum(deltas) / len(deltas)
        print(f"Intervalo medio entre tramas: {promedio:.2f} s")
        print(f"Intervalo mínimo:             {min(deltas):.2f} s")
        print(f"Intervalo máximo:             {max(deltas):.2f} s")
    elif len(mensajes_recibidos) == 1:
        print("Solo se recibió 1 trama durante la ventana de observación.")
    else:
        print("No se recibieron tramas 'inst' en el período.")
    print("=" * 70)


if __name__ == "__main__":
    main()
