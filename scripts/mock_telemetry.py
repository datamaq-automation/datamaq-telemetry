#!/usr/bin/env python3
"""
Generador y Mock de Telemetría Ficticia Inspirada en Datos Reales (Datamaq Telemetry).
Permite poblar la base de datos con historial de 7 días y/o transmitir en vivo vía MQTT.
"""

import argparse
import csv
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

# Asegurar root en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceModel,
    DeviceStatusLogModel,
    FacilityModel,
    OrganizationModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)

CSV_DEFAULT_PATH = "/home/agustin/Descargas/Reporte 22-08-2026 10_48_08 (GMT-3).csv"


class CSVProfileExtractor:
    """Extrae las series y patrones eléctricos del archivo CSV de referencia."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.series_dev1: list[dict[str, float]] = []  # 3 TIs (Medición General ZLC)
        self.series_dev2: list[dict[str, float]] = []  # 2 TIs (Nueva Extra)
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.csv_path):
            print(f"[!] Archivo CSV no encontrado en '{self.csv_path}'. Usando perfil sintético por defecto.")
            self._generate_fallback_profiles()
            return

        with open(self.csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dev_name = row.get("DISPOSITIVO", "").strip()
                try:
                    point = {
                        "ir": float(row.get("Corriente Por Fase (I_R) [A]", 0.0)),
                        "is": float(row.get("Corriente Por Fase (I_S) [A]", 0.0)),
                        "it": float(row.get("Corriente Por Fase (I_T) [A]", 0.0)),
                        "vr": float(row.get("Tension Por Fase (V_R) [V]", 220.0)),
                        "vs": float(row.get("Tension Por Fase (V_S) [V]", 220.0)),
                        "vt": float(row.get("Tension Por Fase (V_T) [V]", 220.0)),
                        "pr": float(row.get("Potencia Activa Por Fase (P_R) [W]", 0.0)),
                        "ps": float(row.get("Potencia Activa Por Fase (P_S) [W]", 0.0)),
                        "pt": float(row.get("Potencia Activa Por Fase (P_T) [W]", 0.0)),
                        "ptot": float(row.get("Potencia Activa Total [W]", 0.0)),
                        "qr": float(row.get("Potencia Reactiva Por Fase (Q_R) [VAr]", 0.0)),
                        "qs": float(row.get("Potencia Reactiva Por Fase (Q_S) [VAr]", 0.0)),
                        "qt": float(row.get("Potencia Reactiva Por Fase (Q_T) [VAr]", 0.0)),
                        "qtot": float(row.get("Potencia Reactiva Total [VAr]", 0.0)),
                    }
                    if "ZLC" in dev_name or "General" in dev_name:
                        self.series_dev1.append(point)
                    else:
                        self.series_dev2.append(point)
                except (ValueError, TypeError):
                    continue

        if not self.series_dev1 or not self.series_dev2:
            self._generate_fallback_profiles()

    def _generate_fallback_profiles(self) -> None:
        # Perfil sintético de respaldo en caso de no encontrar CSV
        for h in range(288):  # 1 día en pasos de 5 min
            factor = 0.5 + 0.5 * math.sin((h / 288) * 2 * math.pi)
            self.series_dev1.append(
                {
                    "ir": 200.0 + 150.0 * factor,
                    "is": 190.0 + 140.0 * factor,
                    "it": 195.0 + 145.0 * factor,
                    "vr": 224.0,
                    "vs": 226.0,
                    "vt": 224.0,
                    "pr": 45000.0 * factor,
                    "ps": 43000.0 * factor,
                    "pt": 44000.0 * factor,
                    "ptot": 132000.0 * factor,
                    "qr": 12000.0 * factor,
                    "qs": 11000.0 * factor,
                    "qt": 11500.0 * factor,
                    "qtot": 34500.0 * factor,
                }
            )
            self.series_dev2.append(
                {
                    "ir": 1.5,
                    "is": 60.0 + 80.0 * factor,
                    "it": 70.0 + 90.0 * factor,
                    "vr": 222.0,
                    "vs": 223.0,
                    "vt": 223.0,
                    "pr": 50.0,
                    "ps": 13000.0 * factor,
                    "pt": 15000.0 * factor,
                    "ptot": 28050.0 * factor,
                    "qr": 10.0,
                    "qs": 3500.0 * factor,
                    "qt": 4000.0 * factor,
                    "qtot": 7510.0 * factor,
                }
            )


def generar_lectura_sintetica(
    base: dict[str, float],
    jitter_pct: float,
    is_two_ti_device: bool = False,
) -> dict[str, Any]:
    """Aplica variaciones gaussianas controladas respetando las leyes eléctricas."""

    def _jitter(val: float, scale: float = 1.0) -> float:
        noise = random.gauss(0, jitter_pct * scale)
        return val * (1.0 + noise)

    # Tensiones (~218V - 230V con leve asimetría)
    vr = round(max(180.0, min(250.0, _jitter(base["vr"], 0.3))), 1)
    vs = round(max(180.0, min(250.0, _jitter(base["vs"], 0.3))), 1)
    vt = round(max(180.0, min(250.0, _jitter(base["vt"], 0.3))), 1)

    # Corrientes
    if is_two_ti_device:
        ir = round(max(0.2, min(3.5, random.uniform(0.8, 2.5))), 1)  # Ruido residual sin TI
        pr = round(max(-50.0, min(100.0, random.uniform(-20.0, 50.0))), 1)
        qr = round(random.uniform(-40.0, 40.0), 1)
    else:
        ir = round(max(10.0, _jitter(base["ir"])), 1)
        pr = round(max(0.0, _jitter(base["pr"])), 1)
        qr = round(_jitter(base["qr"]), 1)

    is_ = round(max(1.0, _jitter(base["is"])), 1)
    it = round(max(1.0, _jitter(base["it"])), 1)

    ps = round(max(0.0, _jitter(base["ps"])), 1)
    pt = round(max(0.0, _jitter(base["pt"])), 1)

    qs = round(_jitter(base["qs"]), 1)
    qt = round(_jitter(base["qt"]), 1)

    # Potencias aparentes y factores de potencia
    def _pot_aparente_y_fp(p: float, q: float) -> tuple[float, float]:
        s = math.sqrt(p * p + q * q)
        fp = round(abs(p) / s, 2) if s > 1.0 else 1.0
        return round(s, 1), min(1.0, max(0.0, fp))

    sr, fpr = _pot_aparente_y_fp(pr, qr)
    ss, fps = _pot_aparente_y_fp(ps, qs)
    st, fpt = _pot_aparente_y_fp(pt, qt)

    # Totales
    p_tot = round(pr + ps + pt, 1)
    q_tot = round(qr + qs + qt, 1)
    s_tot = round(math.sqrt(p_tot * p_tot + q_tot * q_tot), 1)
    fp_tot = round(abs(p_tot) / s_tot, 2) if s_tot > 1.0 else 1.0

    # Desbalance de tensión (VUR)
    desbalance_v = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(vr, vs, vt)

    # Corriente de neutro estimada
    in_val = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(ir, is_, it, pr, ps, pt, qr, qs, qt)
    current_n = in_val.amperios if in_val else None

    return {
        "vr": vr,
        "vs": vs,
        "vt": vt,
        "ir": ir,
        "is": is_,
        "it": it,
        "pr": pr,
        "ps": ps,
        "pt": pt,
        "qr": qr,
        "qs": qs,
        "qt": qt,
        "sr": sr,
        "ss": ss,
        "st": st,
        "fpr": fpr,
        "fps": fps,
        "fpt": fpt,
        "p_tot": p_tot,
        "q_tot": q_tot,
        "s_tot": s_tot,
        "fp_tot": min(1.0, max(0.0, fp_tot)),
        "desbalance_v": desbalance_v,
        "current_n": current_n,
    }


def asegurar_organizacion_y_dispositivos(
    db: Any,
    mac1: str,
    name1: str,
    mac2: str,
    name2: str,
) -> tuple[DeviceModel, DeviceModel]:
    """Crea la organización demo y los dos dispositivos si no existen."""
    # 1. Organización Demo
    org = db.query(OrganizationModel).filter_by(name="Empresa Demo S.A.").first()
    if not org:
        org = OrganizationModel(
            name="Empresa Demo S.A.",
            contact_email="demo@datamaq.com.ar",
            contact_phone="+54 11 5555-0100",
        )
        db.add(org)
        db.flush()

    # 2. Planta Demo
    facility = db.query(FacilityModel).filter_by(organization_id=org.id, name="Planta Piloto").first()
    if not facility:
        facility = FacilityModel(
            organization_id=org.id,
            name="Planta Piloto",
            address="Parque Industrial Pilar, Buenos Aires",
        )
        db.add(facility)
        db.flush()

    # 3. Dispositivo 1 (3 TIs)
    dev1_mac_norm = MacAddress(mac1).valor
    dev1 = db.query(DeviceModel).filter_by(device_uid=dev1_mac_norm).first()
    if not dev1:
        dev1 = DeviceModel(
            facility_id=facility.id,
            device_uid=dev1_mac_norm,
            name=name1,
            model="SmartPlus-3F",
            hw_version="v2.1",
            fw_version="2.4.1",
            tag_location="Tablero General de Entrada (TGBT)",
            estado="ONLINE",
            last_seen_at=datetime.now(timezone.utc),
            installation_type="CONSUMO",
            phases_with_ct="R,S,T",
        )
        db.add(dev1)
    else:
        dev1.name = name1
        dev1.estado = "ONLINE"
        dev1.last_seen_at = datetime.now(timezone.utc)
        dev1.installation_type = "CONSUMO"
        dev1.phases_with_ct = "R,S,T"

    # 4. Dispositivo 2 (2 TIs)
    dev2_mac_norm = MacAddress(mac2).valor
    dev2 = db.query(DeviceModel).filter_by(device_uid=dev2_mac_norm).first()
    if not dev2:
        dev2 = DeviceModel(
            facility_id=facility.id,
            device_uid=dev2_mac_norm,
            name=name2,
            model="SmartPlus-2F",
            hw_version="v2.1",
            fw_version="2.4.1",
            tag_location="Línea de Envasado Extra (2 TIs)",
            estado="ONLINE",
            last_seen_at=datetime.now(timezone.utc),
            installation_type="CONSUMO",
            phases_with_ct="S,T",
        )
        db.add(dev2)
    else:
        dev2.name = name2
        dev2.estado = "ONLINE"
        dev2.last_seen_at = datetime.now(timezone.utc)
        dev2.installation_type = "CONSUMO"
        dev2.phases_with_ct = "S,T"

    db.commit()
    db.refresh(dev1)
    db.refresh(dev2)
    return dev1, dev2


def ejecutar_seed(
    csv_extractor: CSVProfileExtractor,
    days: int = 7,
    step_minutes: int = 5,
    jitter: float = 0.04,
    clear_existing: bool = False,
    mac1: str = "00:11:22:33:44:01",
    name1: str = "Medidor Cabecera (Demo)",
    mac2: str = "00:11:22:33:44:02",
    name2: str = "Medidor Secundario 2-TI (Demo)",
) -> None:
    """Puebla la BD local con el historial ficticio de N días terminando en este instante."""
    print(f"\n[*] === INICIANDO SEED DE TELEMETRÍA FICTICIA ({days} DÍAS) ===")
    session_factory = get_session_factory()
    db = session_factory()

    try:
        dev1, dev2 = asegurar_organizacion_y_dispositivos(db, mac1, name1, mac2, name2)
        print(f"[+] Dispositivo 1 listo: '{dev1.name}' (MAC: {dev1.device_uid}, ID: {dev1.id})")
        print(f"[+] Dispositivo 2 listo: '{dev2.name}' (MAC: {dev2.device_uid}, ID: {dev2.id})")

        if clear_existing:
            print("[*] Limpiando mediciones previas de los dispositivos demo...")
            db.query(TelemetryInstantaneousModel).filter(
                TelemetryInstantaneousModel.device_id.in_([dev1.id, dev2.id])
            ).delete(synchronize_session=False)
            db.query(TelemetryEnergyModel).filter(TelemetryEnergyModel.device_id.in_([dev1.id, dev2.id])).delete(
                synchronize_session=False
            )
            db.query(DeviceStatusLogModel).filter(DeviceStatusLogModel.device_id.in_([dev1.id, dev2.id])).delete(
                synchronize_session=False
            )
            db.query(DeviceAlertModel).filter(DeviceAlertModel.device_id.in_([dev1.id, dev2.id])).delete(
                synchronize_session=False
            )
            db.commit()

        # Generar timestamps
        ahora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        inicio = ahora - timedelta(days=days)
        total_puntos = int((days * 24 * 60) / step_minutes)

        print(f"[*] Generando {total_puntos} puntos temporales desde {inicio.isoformat()} hasta {ahora.isoformat()}...")

        # Contadores base de energía acumulada (kWh ficticios iniciales)
        e_act_kwh_dev1 = 84250.0
        e_react_kvarh_dev1 = 21400.0
        e_act_kwh_dev2 = 23120.0
        e_react_kvarh_dev2 = 6850.0

        batch_inst = []
        batch_energy = []
        batch_logs = []
        delta_hours = step_minutes / 60.0

        len_s1 = len(csv_extractor.series_dev1)
        len_s2 = len(csv_extractor.series_dev2)

        for i in range(total_puntos):
            ts = inicio + timedelta(minutes=i * step_minutes)
            base1 = csv_extractor.series_dev1[i % len_s1]
            base2 = csv_extractor.series_dev2[i % len_s2]

            d1_data = generar_lectura_sintetica(base1, jitter, is_two_ti_device=False)
            d2_data = generar_lectura_sintetica(base2, jitter, is_two_ti_device=True)

            # Integración de energía
            e_act_kwh_dev1 += (d1_data["p_tot"] * delta_hours) / 1000.0
            e_react_kvarh_dev1 += (abs(d1_data["q_tot"]) * delta_hours) / 1000.0
            e_act_kwh_dev2 += (d2_data["p_tot"] * delta_hours) / 1000.0
            e_react_kvarh_dev2 += (abs(d2_data["q_tot"]) * delta_hours) / 1000.0

            # 1. Instantáneas Dev 1
            batch_inst.append(
                TelemetryInstantaneousModel(
                    device_id=dev1.id,
                    recorded_at=ts,
                    voltage_r=Decimal(str(d1_data["vr"])),
                    current_r=Decimal(str(d1_data["ir"])),
                    active_power_r=Decimal(str(d1_data["pr"])),
                    reactive_power_r=Decimal(str(d1_data["qr"])),
                    apparent_power_r=Decimal(str(d1_data["sr"])),
                    power_factor_r=Decimal(str(d1_data["fpr"])),
                    voltage_s=Decimal(str(d1_data["vs"])),
                    current_s=Decimal(str(d1_data["is"])),
                    active_power_s=Decimal(str(d1_data["ps"])),
                    reactive_power_s=Decimal(str(d1_data["qs"])),
                    apparent_power_s=Decimal(str(d1_data["ss"])),
                    power_factor_s=Decimal(str(d1_data["fps"])),
                    voltage_t=Decimal(str(d1_data["vt"])),
                    current_t=Decimal(str(d1_data["it"])),
                    active_power_t=Decimal(str(d1_data["pt"])),
                    reactive_power_t=Decimal(str(d1_data["qt"])),
                    apparent_power_t=Decimal(str(d1_data["st"])),
                    power_factor_t=Decimal(str(d1_data["fpt"])),
                    total_active_power=Decimal(str(d1_data["p_tot"])),
                    total_reactive_power=Decimal(str(d1_data["q_tot"])),
                    total_apparent_power=Decimal(str(d1_data["s_tot"])),
                    total_power_factor=Decimal(str(d1_data["fp_tot"])),
                    desbalance_tension_porcentaje=Decimal(str(d1_data["desbalance_v"]))
                    if d1_data["desbalance_v"] is not None
                    else None,
                    current_n=Decimal(str(d1_data["current_n"])) if d1_data["current_n"] is not None else None,
                )
            )

            # 2. Instantáneas Dev 2
            batch_inst.append(
                TelemetryInstantaneousModel(
                    device_id=dev2.id,
                    recorded_at=ts,
                    voltage_r=Decimal(str(d2_data["vr"])),
                    current_r=Decimal(str(d2_data["ir"])),
                    active_power_r=Decimal(str(d2_data["pr"])),
                    reactive_power_r=Decimal(str(d2_data["qr"])),
                    apparent_power_r=Decimal(str(d2_data["sr"])),
                    power_factor_r=Decimal(str(d2_data["fpr"])),
                    voltage_s=Decimal(str(d2_data["vs"])),
                    current_s=Decimal(str(d2_data["is"])),
                    active_power_s=Decimal(str(d2_data["ps"])),
                    reactive_power_s=Decimal(str(d2_data["qs"])),
                    apparent_power_s=Decimal(str(d2_data["ss"])),
                    power_factor_s=Decimal(str(d2_data["fps"])),
                    voltage_t=Decimal(str(d2_data["vt"])),
                    current_t=Decimal(str(d2_data["it"])),
                    active_power_t=Decimal(str(d2_data["pt"])),
                    reactive_power_t=Decimal(str(d2_data["qt"])),
                    apparent_power_t=Decimal(str(d2_data["st"])),
                    power_factor_t=Decimal(str(d2_data["fpt"])),
                    total_active_power=Decimal(str(d2_data["p_tot"])),
                    total_reactive_power=Decimal(str(d2_data["q_tot"])),
                    total_apparent_power=Decimal(str(d2_data["s_tot"])),
                    total_power_factor=Decimal(str(d2_data["fp_tot"])),
                    desbalance_tension_porcentaje=Decimal(str(d2_data["desbalance_v"]))
                    if d2_data["desbalance_v"] is not None
                    else None,
                    current_n=Decimal(str(d2_data["current_n"])) if d2_data["current_n"] is not None else None,
                )
            )

            # 3. Energías Acumuladas
            batch_energy.append(
                TelemetryEnergyModel(
                    device_id=dev1.id,
                    recorded_at=ts,
                    net_active_energy_kwh=Decimal(f"{e_act_kwh_dev1:.2f}"),
                    imported_active_energy_kwh=Decimal(f"{e_act_kwh_dev1:.2f}"),
                    exported_active_energy_kwh=Decimal("0.00"),
                    net_reactive_energy_kvarh=Decimal(f"{e_react_kvarh_dev1:.2f}"),
                    imported_reactive_energy_kvarh=Decimal(f"{e_react_kvarh_dev1:.2f}"),
                    exported_reactive_energy_kvarh=Decimal("0.00"),
                )
            )
            batch_energy.append(
                TelemetryEnergyModel(
                    device_id=dev2.id,
                    recorded_at=ts,
                    net_active_energy_kwh=Decimal(f"{e_act_kwh_dev2:.2f}"),
                    imported_active_energy_kwh=Decimal(f"{e_act_kwh_dev2:.2f}"),
                    exported_active_energy_kwh=Decimal("0.00"),
                    net_reactive_energy_kvarh=Decimal(f"{e_react_kvarh_dev2:.2f}"),
                    imported_reactive_energy_kvarh=Decimal(f"{e_react_kvarh_dev2:.2f}"),
                    exported_reactive_energy_kvarh=Decimal("0.00"),
                )
            )

            # 4. Status log cada hora
            if i % 12 == 0:
                batch_logs.append(
                    DeviceStatusLogModel(
                        device_id=dev1.id,
                        recorded_at=ts,
                        wifi_rssi_dbm=random.randint(-72, -58),
                        wifi_calidad=random.randint(80, 95),
                        ip_address="192.168.1.150",
                        uptime_seconds=i * step_minutes * 60,
                        raw_payload={"status": "OK", "model": "SmartPlus-3F"},
                    )
                )
                batch_logs.append(
                    DeviceStatusLogModel(
                        device_id=dev2.id,
                        recorded_at=ts,
                        wifi_rssi_dbm=random.randint(-78, -65),
                        wifi_calidad=random.randint(70, 88),
                        ip_address="192.168.1.151",
                        uptime_seconds=i * step_minutes * 60,
                        raw_payload={"status": "OK", "model": "SmartPlus-2F"},
                    )
                )

            # Inserción en lotes de 1000 para optimizar rendimiento
            if len(batch_inst) >= 1000:
                db.bulk_save_objects(batch_inst)
                db.bulk_save_objects(batch_energy)
                if batch_logs:
                    db.bulk_save_objects(batch_logs)
                db.commit()
                batch_inst.clear()
                batch_energy.clear()
                batch_logs.clear()
                print(f"  [+] Guardados {i * 2} / {total_puntos * 2} registros...")

        if batch_inst:
            db.bulk_save_objects(batch_inst)
            db.bulk_save_objects(batch_energy)
            if batch_logs:
                db.bulk_save_objects(batch_logs)
            db.commit()

        # Actualizar last_seen_at
        dev1.last_seen_at = ahora
        dev2.last_seen_at = ahora
        db.commit()

        print("\n" + "=" * 65)
        print("          ✓ SEED DE TELEMETRÍA FINALIZADO CON ÉXITO")
        print("=" * 65)
        print(f"• Total Puntos Insertados:  {total_puntos * 2} instantáneas + {total_puntos * 2} energías")
        print(
            f"• Rango Temporal:           {inicio.strftime('%Y-%m-%d %H:%M')} a {ahora.strftime('%Y-%m-%d %H:%M')} (UTC)"
        )
        print(f"• Dispositivo 1 (3 TIs):    MAC={dev1.device_uid} | ID={dev1.id}")
        print(f"• Dispositivo 2 (2 TIs):    MAC={dev2.device_uid} | ID={dev2.id}")
        print("\n• URLs para probar en tu Frontend o REST Client:")
        print(f"  - Latest Dev 1: GET /api/v1/telemetria/dispositivos/{dev1.device_uid}/latest")
        print(f"  - Latest Dev 2: GET /api/v1/telemetria/dispositivos/{dev2.device_uid}/latest")
        print(f"  - Gráficos Dev 1: GET /api/v1/telemetria/dispositivos/{dev1.device_uid}/instantaneas?limite=288")
        print(f"  - Gráficos Dev 2: GET /api/v1/telemetria/dispositivos/{dev2.device_uid}/instantaneas?limite=288")
        print("=" * 65 + "\n")

    except Exception as e:
        db.rollback()
        print(f"[!] Error durante el seed: {e}", file=sys.stderr)
        raise e
    finally:
        db.close()


def ejecutar_live_replay(
    csv_extractor: CSVProfileExtractor,
    interval: float = 2.0,
    jitter: float = 0.04,
    mac1: str = "00:11:22:33:44:01",
    name1: str = "Medidor Cabecera (Demo)",
    mac2: str = "00:11:22:33:44:02",
    name2: str = "Medidor Secundario 2-TI (Demo)",
    broker_host: str | None = None,
    broker_port: int | None = None,
) -> None:
    """Publica continuamente telemetría MQTT simulando los dos medidores en tiempo real."""
    settings = get_settings()
    host = broker_host or settings.MQTT_BROKER_HOST
    port = broker_port or settings.MQTT_BROKER_PORT

    mac1_raw = MacAddress(mac1).valor
    mac2_raw = MacAddress(mac2).valor

    print("\n[*] === INICIANDO TRANSMISIÓN MQTT EN VIVO ===")
    print(f"[*] Conectando al broker MQTT en {host}:{port}...")

    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id="datamaq-mock-generator",
        clean_session=True,
    )
    if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
        print("[+] Conexión establecida con el broker.")
    except Exception as e:
        print(f"[!] No se pudo conectar al broker MQTT ({e}). Verifique que Mosquitto esté corriendo.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Transmitiendo cada {interval}s. Presione Ctrl+C para detener.\n")

    len_s1 = len(csv_extractor.series_dev1)
    len_s2 = len(csv_extractor.series_dev2)
    step = 0

    e_act_kwh_dev1 = 85200.0
    e_act_kwh_dev2 = 24100.0

    try:
        while True:
            ahora_ts = int(time.time())
            base1 = csv_extractor.series_dev1[step % len_s1]
            base2 = csv_extractor.series_dev2[step % len_s2]

            d1 = generar_lectura_sintetica(base1, jitter, is_two_ti_device=False)
            d2 = generar_lectura_sintetica(base2, jitter, is_two_ti_device=True)

            e_act_kwh_dev1 += (d1["p_tot"] * (interval / 3600.0)) / 1000.0
            e_act_kwh_dev2 += (d2["p_tot"] * (interval / 3600.0)) / 1000.0

            # Payload estándar Powermeter
            import json

            payload1 = {
                "timestamp": ahora_ts,
                "device_info": {
                    "device_name": name1,
                    "serial_number": f"SN-{mac1_raw[-6:]}",
                    "device_model": "SmartPlus-3F",
                    "hw_model": "ESP32",
                    "device_fw": "2.4.1",
                    "uptime": step * int(interval),
                },
                "f": [
                    {
                        "n": "R",
                        "v": d1["vr"],
                        "i": d1["ir"],
                        "p": d1["pr"],
                        "q": d1["qr"],
                        "s": d1["sr"],
                        "pf": d1["fpr"],
                    },
                    {
                        "n": "S",
                        "v": d1["vs"],
                        "i": d1["is"],
                        "p": d1["ps"],
                        "q": d1["qs"],
                        "s": d1["ss"],
                        "pf": d1["fps"],
                    },
                    {
                        "n": "T",
                        "v": d1["vt"],
                        "i": d1["it"],
                        "p": d1["pt"],
                        "q": d1["qt"],
                        "s": d1["st"],
                        "pf": d1["fpt"],
                    },
                ],
                "total": {
                    "p": d1["p_tot"],
                    "q": d1["q_tot"],
                    "s": d1["s_tot"],
                    "pf": d1["fp_tot"],
                },
            }

            payload2 = {
                "timestamp": ahora_ts,
                "device_info": {
                    "device_name": name2,
                    "serial_number": f"SN-{mac2_raw[-6:]}",
                    "device_model": "SmartPlus-2F",
                    "hw_model": "ESP32",
                    "device_fw": "2.4.1",
                    "uptime": step * int(interval),
                },
                "f": [
                    {
                        "n": "R",
                        "v": d2["vr"],
                        "i": d2["ir"],
                        "p": d2["pr"],
                        "q": d2["qr"],
                        "s": d2["sr"],
                        "pf": d2["fpr"],
                    },
                    {
                        "n": "S",
                        "v": d2["vs"],
                        "i": d2["is"],
                        "p": d2["ps"],
                        "q": d2["qs"],
                        "s": d2["ss"],
                        "pf": d2["fps"],
                    },
                    {
                        "n": "T",
                        "v": d2["vt"],
                        "i": d2["it"],
                        "p": d2["pt"],
                        "q": d2["qt"],
                        "s": d2["st"],
                        "pf": d2["fpt"],
                    },
                ],
                "total": {
                    "p": d2["p_tot"],
                    "q": d2["q_tot"],
                    "s": d2["s_tot"],
                    "pf": d2["fp_tot"],
                },
            }

            topic1 = f"m/wifi/{mac1_raw}/inst"
            topic2 = f"m/wifi/{mac2_raw}/inst"

            client.publish(topic1, json.dumps(payload1), qos=1)
            client.publish(topic2, json.dumps(payload2), qos=1)

            # Publicar energía periódica
            if step % 5 == 0:
                acc1 = {"timestamp": ahora_ts, "total": {"net_active_energy_KWH": round(e_act_kwh_dev1, 2)}}
                acc2 = {"timestamp": ahora_ts, "total": {"net_active_energy_KWH": round(e_act_kwh_dev2, 2)}}
                client.publish(f"m/wifi/{mac1_raw}/acc", json.dumps(acc1), qos=1)
                client.publish(f"m/wifi/{mac2_raw}/acc", json.dumps(acc2), qos=1)

            print(
                f"\r[⚡ LIVE {datetime.now().strftime('%H:%M:%S')}] "
                f"Dev1 (3-TI): {d1['p_tot'] / 1000.0:.1f} kW, {d1['ir']}A/{d1['is']}A/{d1['it']}A, VUR={d1['desbalance_v']}% | "
                f"Dev2 (2-TI): {d2['p_tot'] / 1000.0:.1f} kW, {d2['ir']}A/{d2['is']}A/{d2['it']}A, VUR={d2['desbalance_v']}%",
                end="",
                flush=True,
            )

            step += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[*] Transmisión en vivo detenida.")
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generador y Mock de Telemetría Ficticia Inspirada en Datos Reales para Frontend Testing."
    )
    parser.add_argument(
        "--csv-path",
        default=CSV_DEFAULT_PATH,
        help=f"Ruta al archivo CSV de referencia (default: {CSV_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--mode",
        choices=["seed", "live", "both"],
        default="seed",
        help="Modo de ejecución: 'seed' (poblar BD), 'live' (transmitir MQTT), o 'both' (ambos).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Cantidad de días de historial a generar en modo seed (default: 7)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Intervalo en segundos entre mensajes en modo live (default: 2.0)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.04,
        help="Porcentaje de fluctuación aleatoria gaussiana (default: 0.04 = ±4%%)",
    )
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Elimina mediciones previas de los dispositivos demo antes de insertar.",
    )
    parser.add_argument(
        "--mac1",
        default="00:11:22:33:44:01",
        help="MAC address ficticia del Dispositivo 1 (3 TIs)",
    )
    parser.add_argument(
        "--name1",
        default="Medidor Cabecera (Demo)",
        help="Nombre del Dispositivo 1 (3 TIs)",
    )
    parser.add_argument(
        "--mac2",
        default="00:11:22:33:44:02",
        help="MAC address ficticia del Dispositivo 2 (2 TIs)",
    )
    parser.add_argument(
        "--name2",
        default="Medidor Secundario 2-TI (Demo)",
        help="Nombre del Dispositivo 2 (2 TIs)",
    )
    parser.add_argument(
        "--broker-host",
        help="Host del broker MQTT (opcional, por defecto toma la config del proyecto)",
    )
    parser.add_argument(
        "--broker-port",
        type=int,
        help="Puerto del broker MQTT (opcional, por defecto toma la config del proyecto)",
    )

    args = parser.parse_args()

    print("[*] Leyendo perfil de referencia desde el CSV...")
    extractor = CSVProfileExtractor(args.csv_path)
    print(
        f"[+] Perfiles cargados: Dev1 (3-TI) con {len(extractor.series_dev1)} puntos, "
        f"Dev2 (2-TI) con {len(extractor.series_dev2)} puntos."
    )

    if args.mode in ("seed", "both"):
        ejecutar_seed(
            csv_extractor=extractor,
            days=args.days,
            step_minutes=5,
            jitter=args.jitter,
            clear_existing=args.clear_existing,
            mac1=args.mac1,
            name1=args.name1,
            mac2=args.mac2,
            name2=args.name2,
        )

    if args.mode in ("live", "both"):
        ejecutar_live_replay(
            csv_extractor=extractor,
            interval=args.interval,
            jitter=args.jitter,
            mac1=args.mac1,
            name1=args.name1,
            mac2=args.mac2,
            name2=args.name2,
            broker_host=args.broker_host,
            broker_port=args.broker_port,
        )


if __name__ == "__main__":
    main()
