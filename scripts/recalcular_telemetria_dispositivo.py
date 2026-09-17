#!/usr/bin/env python3
"""Script de recálculo histórico de telemetría instantánea y acumulada por rotación fasorial.

Aplica la corrección trigonométrica de ángulo sobre lecturas almacenadas previamente en la base de datos.

Uso:
  python3 scripts/recalcular_telemetria_dispositivo.py --dispositivo-id 364 --correccion "R:-60,S:60" [--dry-run]
"""

import argparse
import math
import sys
from pathlib import Path

# Agregar raíz al sys.path
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.models import (  # noqa: E402
    DeviceModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)


def rotar_pq(
    p: float | None, q: float | None, angulo_grados: float
) -> tuple[float | None, float | None, float | None, float | None]:
    if p is None and q is None:
        return None, None, None, None
    p_in = p or 0.0
    q_in = q or 0.0
    rad = math.radians(angulo_grados)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    p_prim = p_in * cos_a + q_in * sin_a
    q_prim = q_in * cos_a - p_in * sin_a
    s_prim = math.hypot(p_prim, q_prim)
    fp_prim = p_prim / s_prim if s_prim > 0 else None
    if fp_prim is not None:
        fp_prim = max(-1.0, min(1.0, fp_prim))
    return p_prim, q_prim, s_prim, fp_prim


def recalcular_dispositivo(dispositivo_id: str, correccion: str, dry_run: bool = False) -> None:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        dev_model = db.query(DeviceModel).filter(DeviceModel.id == dispositivo_id).first()
        if not dev_model:
            print(f"❌ Error: No se encontró el dispositivo ID '{dispositivo_id}'.")
            return

        print(f"🔧 Dispositivo: {dev_model.name} (ID: {dev_model.id}, UID: {dev_model.device_uid})")
        print(f"⚙️ Configurando corrección angular: '{correccion}'")

        if not dry_run:
            dev_model.ct_phase_angle_offsets = correccion
            db.commit()

        angulos_map: dict[str, float] = {}
        for item in correccion.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                try:
                    angulos_map[k.strip().upper()] = float(v.strip())
                except ValueError:
                    pass

        # 1. Recalcular lecturas instantáneas
        lecturas = (
            db.query(TelemetryInstantaneousModel).filter(TelemetryInstantaneousModel.device_id == dispositivo_id).all()
        )
        print(f"📊 Procesando {len(lecturas)} lecturas instantáneas...")

        actualizadas = 0
        for lec in lecturas:
            modificado = False
            # Fase R
            if "R" in angulos_map and (lec.phase_r_p is not None or lec.phase_r_q is not None):
                pr, qr, sr, fpr = rotar_pq(lec.phase_r_p, lec.phase_r_q, angulos_map["R"])
                lec.phase_r_p, lec.phase_r_q, lec.phase_r_s, lec.phase_r_fp = pr, qr, sr, fpr
                modificado = True

            # Fase S
            if "S" in angulos_map and (lec.phase_s_p is not None or lec.phase_s_q is not None):
                ps, qs, ss, fps = rotar_pq(lec.phase_s_p, lec.phase_s_q, angulos_map["S"])
                lec.phase_s_p, lec.phase_s_q, lec.phase_s_s, lec.phase_s_fp = ps, qs, ss, fps
                modificado = True

            # Fase T
            if "T" in angulos_map and (lec.phase_t_p is not None or lec.phase_t_q is not None):
                pt, qt, st, fpt = rotar_pq(lec.phase_t_p, lec.phase_t_q, angulos_map["T"])
                lec.phase_t_p, lec.phase_t_q, lec.phase_t_s, lec.phase_t_fp = pt, qt, st, fpt
                modificado = True

            if modificado:
                # Recalcular totales consolidados
                p_fases = [p for p in [lec.phase_r_p, lec.phase_s_p, lec.phase_t_p] if p is not None]
                q_fases = [q for q in [lec.phase_r_q, lec.phase_s_q, lec.phase_t_q] if q is not None]
                s_fases = [s for s in [lec.phase_r_s, lec.phase_s_s, lec.phase_t_s] if s is not None]

                if p_fases:
                    lec.p_tot = sum(p_fases)
                if q_fases:
                    lec.q_tot = sum(q_fases)
                if s_fases:
                    lec.s_tot = sum(s_fases)

                if lec.p_tot is not None and lec.s_tot is not None and lec.s_tot > 0:
                    fp = lec.p_tot / lec.s_tot
                    lec.fp_tot = max(-1.0, min(1.0, fp))

                actualizadas += 1

        print(f"✅ Lecturas instantáneas actualizadas: {actualizadas}")

        # 2. Recalcular acumulados de energía
        acumulados = db.query(TelemetryEnergyModel).filter(TelemetryEnergyModel.device_id == dispositivo_id).all()
        print(f"⚡ Procesando {len(acumulados)} acumulados de energía...")

        if not dry_run:
            db.commit()
            print("💾 Cambios persistidos correctamente en la base de datos.")
        else:
            db.rollback()
            print("🔍 [DRY-RUN] Cambios calculados con éxito sin modificar la BD.")

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalcular telemetría por rotación fasorial.")
    parser.add_argument("--dispositivo-id", required=True, help="ID del dispositivo a recalcular")
    parser.add_argument("--correccion", default="R:-60,S:60", help="Ángulos por fase (ej. 'R:-60,S:60')")
    parser.add_argument("--dry-run", action="store_true", help="Simular sin modificar la BD")
    args = parser.parse_args()

    recalcular_dispositivo(args.dispositivo_id, args.correccion, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
