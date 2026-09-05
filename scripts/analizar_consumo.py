"""Batch de detección de episodios y atribución de consumo por carga.

Pensado para correr por timer de systemd (ver `systemd/datamaq-analisis.timer`) o a mano.
Es idempotente: re-correr la misma ventana reescribe sus intervalos en vez de duplicarlos,
y nunca pisa una corrección humana.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.use_cases.atribuir_consumo import AtribuirConsumoUseCase
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLCargasRepository,
    MySQLDispositivosRepository,
    MySQLIntervalosActividadRepository,
    MySQLSeriePotenciaRepository,
)

logger = get_logger("analizar_consumo")


def parsear_fecha(valor: str) -> datetime:
    """ISO 8601. Un valor sin offset se interpreta como UTC."""
    fecha = datetime.fromisoformat(valor)
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=None, help="UUID del dispositivo. Sin esto, procesa todos.")
    parser.add_argument("--dias", type=int, default=7, help="Ventana hacia atrás si no se dan fechas.")
    parser.add_argument("--desde", type=str, default=None, help="Inicio explícito de la ventana (ISO).")
    parser.add_argument("--hasta", type=str, default=None, help="Fin explícito de la ventana (ISO).")
    args = parser.parse_args()

    db = get_session_factory()()
    try:
        use_case = AtribuirConsumoUseCase(
            repo_serie=MySQLSeriePotenciaRepository(db),
            repo_cargas=MySQLCargasRepository(db),
            repo_intervalos=MySQLIntervalosActividadRepository(db),
        )
        ids = [args.device] if args.device else [d.id for d in MySQLDispositivosRepository(db).listar()]
        desde = parsear_fecha(args.desde) if args.desde else None
        hasta = parsear_fecha(args.hasta) if args.hasta else None

        for dispositivo_id in ids:
            resultado = use_case.analizar(dispositivo_id, desde=desde, hasta=hasta, dias=args.dias)
            logger.info(
                "analisis_consumo_completado",
                dispositivo_id=dispositivo_id,
                lecturas=resultado.cantidad_lecturas,
                episodios=resultado.episodios_detectados,
                atribuidos=resultado.atribuidos,
                no_atribuidos=resultado.no_atribuidos,
                cargas_con_firma=resultado.cargas_con_firma,
            )
        return 0
    except Exception as e:
        logger.error("analisis_consumo_fallido", error=str(e), exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
