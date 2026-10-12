"""scripts/consolidar_alertas_duplicadas.py — Consolida las alertas abiertas duplicadas (#19).

Antes de #19, cada detección abría una alerta nueva: un medidor de Durax acumuló 116 SOBRECOMPENSACION_REACTIVA
abiertas a la vez. Por cada grupo abierto de (dispositivo, tipo, fase) con más de una alerta, deja la más antigua
con las ocurrencias sumadas, la última detección y los valores de la detección más reciente, y resuelve las demás
con la observación "Consolidada en la alerta #<id>".

Es idempotente: una segunda corrida no encuentra grupos con más de una abierta. Por defecto solo informa
(dry-run). Escribe en la base únicamente con --aplicar, y correrlo en producción lo autoriza el dueño.
Los dispositivos desactivados (is_active=0) se excluyen salvo --incluir-inactivos: sus alertas esperan una
decisión del dueño.

Uso:
    python -m scripts.consolidar_alertas_duplicadas               # dry-run
    python -m scripts.consolidar_alertas_duplicadas --aplicar
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby

from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.models import DeviceAlertModel, DeviceModel


@dataclass(frozen=True)
class GrupoConsolidado:
    device_id: str
    alert_type: str
    phase: str | None
    conservada_id: int
    resueltas_ids: tuple[int, ...]
    ocurrencias: int


def _clave(a: DeviceAlertModel) -> tuple[str, str, str]:
    return (a.device_id, a.alert_type, a.phase or "")


def _ultima_deteccion(a: DeviceAlertModel) -> datetime:
    return a.last_detected_at or a.triggered_at


def consolidar(db: Session, aplicar: bool, ahora: datetime, incluir_inactivos: bool = False) -> list[GrupoConsolidado]:
    """Consolida en la sesión y hace commit solo con `aplicar`; si no, rollback. Devuelve lo consolidado."""
    consulta = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False))
    if not incluir_inactivos:
        consulta = consulta.join(DeviceModel, DeviceModel.id == DeviceAlertModel.device_id).filter(
            DeviceModel.esta_activo.is_(True)
        )
    abiertas = sorted(consulta.all(), key=lambda a: (_clave(a), a.triggered_at, a.id))

    grupos: list[GrupoConsolidado] = []
    for _, filas in groupby(abiertas, key=_clave):
        grupo = list(filas)
        if len(grupo) < 2:
            continue
        conservada, duplicadas = grupo[0], grupo[1:]
        mas_reciente = max(grupo, key=_ultima_deteccion)
        ocurrencias = sum(a.occurrences or 1 for a in grupo)

        conservada.occurrences = ocurrencias
        conservada.last_detected_at = _ultima_deteccion(mas_reciente)
        conservada.message = mas_reciente.message
        conservada.severity = mas_reciente.severity
        conservada.measured_value = mas_reciente.measured_value
        conservada.threshold_value = mas_reciente.threshold_value
        for d in duplicadas:
            d.is_resolved = True
            d.resolved_at = ahora
            nota = f"Consolidada en la alerta #{conservada.id} (#19)."
            d.notes = f"{d.notes} | {nota}" if d.notes else nota

        grupos.append(
            GrupoConsolidado(
                device_id=conservada.device_id,
                alert_type=conservada.alert_type,
                phase=conservada.phase,
                conservada_id=conservada.id,
                resueltas_ids=tuple(d.id for d in duplicadas),
                ocurrencias=ocurrencias,
            )
        )

    if aplicar:
        db.commit()
    else:
        db.rollback()
    return grupos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="escribe en la base (sin esto, solo informa)")
    parser.add_argument("--incluir-inactivos", action="store_true", help="incluye dispositivos con is_active=0")
    args = parser.parse_args()

    from src.infrastructure.sqlalchemy.database import get_session_factory

    db = get_session_factory()()
    try:
        grupos = consolidar(db, args.aplicar, datetime.now(timezone.utc), args.incluir_inactivos)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "DRY-RUN (sin cambios; --aplicar para escribir)"
    print(f"{modo}: {len(grupos)} grupos, {sum(len(g.resueltas_ids) for g in grupos)} alertas a resolver.")
    for g in grupos:
        fase = f" fase {g.phase}" if g.phase else ""
        print(
            f"  {g.device_id} {g.alert_type}{fase}: conserva #{g.conservada_id} "
            f"({g.ocurrencias} ocurrencias), resuelve {len(g.resueltas_ids)}"
        )


if __name__ == "__main__":
    main()
