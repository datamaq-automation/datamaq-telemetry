"""Batch de descubrimiento y propuesta de firmas INFERIDA de cargas.

Consulta energy-ml para cada dispositivo en un rango temporal, empareja candidatas
con el catálogo, propone firmas nuevas y actualiza las existentes (respetando CAMPANA).

Idempotente: re-correr la misma ventana actualiza las propuestas sin duplicarlos.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.cargas.exceptions import DescubridorNoDisponibleError

from src.application.use_cases.proponer_firmas_inferidas import (
    ProponerFirmasInferidasUseCase,
)
from src.infrastructure.energy_ml.descubridor_http import EnergyMlHttpDescubridor
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLCargasRepository, MySQLDispositivosRepository

logger = get_logger("proponer_firmas")


def parsear_fecha(valor: str) -> datetime:
    """ISO 8601. Un valor sin offset se interpreta como UTC."""
    fecha = datetime.fromisoformat(valor)
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=None, help="UUID del dispositivo. Sin esto, procesa todos.")
    parser.add_argument("--dias", type=int, default=30, help="Ventana hacia atrás si no se dan fechas.")
    parser.add_argument("--desde", type=str, default=None, help="Inicio explícito de la ventana (ISO).")
    parser.add_argument("--hasta", type=str, default=None, help="Fin explícito de la ventana (ISO).")
    args = parser.parse_args()

    db = get_session_factory()()
    settings = get_settings()
    try:
        use_case = ProponerFirmasInferidasUseCase(
            cargas=MySQLCargasRepository(db),
            descubridor=EnergyMlHttpDescubridor(
                base_url=settings.ENERGY_ML_URL, timeout_s=settings.ENERGY_ML_TIMEOUT_S
            ),
        )
        repo_dispositivos = MySQLDispositivosRepository(db)
        ids = [args.device] if args.device else [d.id for d in repo_dispositivos.listar()]

        desde = parsear_fecha(args.desde) if args.desde else None
        hasta = parsear_fecha(args.hasta) if args.hasta else None

        if hasta is None:
            hasta = datetime.now(timezone.utc)
        if desde is None:
            desde = hasta - timedelta(days=args.dias)

        fallidos = 0
        exitos = 0

        for dispositivo_id in ids:
            dispositivo = repo_dispositivos.obtener_por_id(dispositivo_id)
            if not dispositivo:
                logger.warning("dispositivo_no_encontrado", dispositivo_id=dispositivo_id)
                continue

            try:
                resultado = use_case.execute(dispositivo_id, dispositivo.nombre, desde, hasta)
                logger.info(
                    "propuesta_firmas_completada",
                    dispositivo_id=dispositivo_id,
                    dispositivo_nombre=dispositivo.nombre,
                    actualizadas=len(resultado.actualizadas),
                    creadas=len(resultado.creadas),
                    protegidas=len(resultado.protegidas),
                    descartadas=resultado.descartadas,
                )
                exitos += 1
            except DescubridorNoDisponibleError as e:
                logger.warning(
                    "descubridor_no_disponible",
                    dispositivo_id=dispositivo_id,
                    dispositivo_nombre=dispositivo.nombre,
                    error=str(e),
                )
                fallidos += 1
            except Exception as e:
                logger.error(
                    "propuesta_firmas_fallida",
                    dispositivo_id=dispositivo_id,
                    dispositivo_nombre=dispositivo.nombre,
                    error=str(e),
                    exc_info=True,
                )
                fallidos += 1

        if exitos == 0 and fallidos > 0:
            logger.error("todas_propuestas_fallaron", total=fallidos)
            return 1

        logger.info("propuesta_firmas_batch_completada", exitos=exitos, fallidos=fallidos)
        return 0

    except Exception as e:
        logger.error("propuesta_firmas_batch_fallido", error=str(e), exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
