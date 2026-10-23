"""scripts/sanear_alertas_huerfanas_pre_dedup.py — Saneamiento retroactivo de alertas huérfanas pre-deduplicación.

Identifica alertas abiertas duplicadas para el mismo (dispositivo_id, tipo_alerta, fase),
conservando únicamente la más antigua (disparada_en) y marcando las excedentes como
resueltas con resuelta_en = NOW(), estado = 'RESUELTA', observaciones: "Saneamiento retroactivo pre-Issue #19".

Ejecuta en modo --dry-run por defecto. Para persistir los cambios se requiere el flag --aplicar.

Uso:
    python -m scripts.sanear_alertas_huerfanas_pre_dedup              # dry-run
    python -m scripts.sanear_alertas_huerfanas_pre_dedup --aplicar    # escribe en la base de datos
    python -m scripts.sanear_alertas_huerfanas_pre_dedup --dispositivo F8B3B7C0BBB0
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby

from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.models import DeviceAlertModel


@dataclass(frozen=True)
class GrupoSaneado:
    device_id: str
    alert_type: str
    phase: str | None
    conservada_id: int
    resueltas_ids: tuple[int, ...]
    ocurrencias_totales: int


def _clave(a: DeviceAlertModel) -> tuple[str, str, str]:
    return (a.device_id, a.alert_type, a.phase or "")


def _ultima_deteccion(a: DeviceAlertModel) -> datetime:
    return a.last_detected_at or a.triggered_at


def sanear_alertas_huerfanas(
    db: Session,
    aplicar: bool = False,
    ahora: datetime | None = None,
    dispositivo_id: str | None = None,
    tipo_alerta: str | None = None,
) -> list[GrupoSaneado]:
    """Identifica y resuelve alertas abiertas duplicadas dejando la más antigua activa.

    Si `aplicar` es False, ejecuta un rollback (dry-run).
    Si `aplicar` es True, commitea los cambios a la base de datos.
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    consulta = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False))
    if dispositivo_id:
        consulta = consulta.filter(DeviceAlertModel.device_id == dispositivo_id)
    if tipo_alerta:
        consulta = consulta.filter(DeviceAlertModel.alert_type == tipo_alerta)

    # Ordenar por clave, triggered_at ascendente (más antigua primero) y luego id
    abiertas = sorted(consulta.all(), key=lambda a: (_clave(a), a.triggered_at, a.id))

    grupos: list[GrupoSaneado] = []
    for _, filas in groupby(abiertas, key=_clave):
        grupo = list(filas)
        if len(grupo) < 2:
            continue

        conservada, duplicadas = grupo[0], grupo[1:]
        mas_reciente = max(grupo, key=_ultima_deteccion)
        ocurrencias_totales = sum(a.occurrences or 1 for a in grupo)

        # Actualizar la alerta conservada con el acumulado histórico
        conservada.occurrences = ocurrencias_totales
        conservada.last_detected_at = _ultima_deteccion(mas_reciente)
        conservada.message = mas_reciente.message
        conservada.severity = mas_reciente.severity
        conservada.measured_value = mas_reciente.measured_value
        conservada.threshold_value = mas_reciente.threshold_value

        # Marcar las duplicadas como resueltas
        nota = "Saneamiento retroactivo pre-Issue #19"
        for d in duplicadas:
            d.is_resolved = True
            d.resolved_at = ahora
            d.notes = f"{d.notes} | {nota}" if d.notes else nota

        grupos.append(
            GrupoSaneado(
                device_id=conservada.device_id,
                alert_type=conservada.alert_type,
                phase=conservada.phase,
                conservada_id=conservada.id,
                resueltas_ids=tuple(d.id for d in duplicadas),
                ocurrencias_totales=ocurrencias_totales,
            )
        )

    if aplicar:
        db.commit()
    else:
        db.rollback()

    return grupos


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Aplica los cambios en la base de datos (por defecto es dry-run / simulación)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo simulación explícito (comportamiento predeterminado)",
    )
    parser.add_argument(
        "--dispositivo",
        type=str,
        default=None,
        help="Filtrar por device_id puntual",
    )
    parser.add_argument(
        "--tipo-alerta",
        type=str,
        default=None,
        help="Filtrar por tipo de alerta puntual (ej. SOBRECOMPENSACION_REACTIVA)",
    )
    args = parser.parse_args()

    # Si se pasa --dry-run explícito, anula --aplicar
    modo_aplicar = args.aplicar and not args.dry_run

    from src.infrastructure.sqlalchemy.database import get_session_factory

    db = get_session_factory()()
    try:
        grupos = sanear_alertas_huerfanas(
            db=db,
            aplicar=modo_aplicar,
            dispositivo_id=args.dispositivo,
            tipo_alerta=args.tipo_alerta,
        )
    finally:
        db.close()

    modo_str = "APLICADO" if modo_aplicar else "DRY-RUN (sin cambios; usar --aplicar para persistir)"
    total_resueltas = sum(len(g.resueltas_ids) for g in grupos)
    print(f"{modo_str}: {len(grupos)} grupos duplicados encontrados, {total_resueltas} alertas a resolver.")
    for g in grupos:
        fase = f" fase {g.phase}" if g.phase else ""
        print(
            f"  Dispositivo {g.device_id} | {g.alert_type}{fase}: "
            f"conserva #{g.conservada_id} ({g.ocurrencias_totales} ocurrencias totales), "
            f"resuelve {len(g.resueltas_ids)} duplicadas (IDs: {list(g.resueltas_ids)})"
        )


if __name__ == "__main__":
    main()
