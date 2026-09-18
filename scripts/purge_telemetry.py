import argparse
import os
import sys
from datetime import datetime, timezone

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLTelemetriaRepository


def parsear_corte_hasta(valor: str) -> datetime:
    """Convierte un string ISO en un datetime UTC *aware*.

    Un valor sin offset (naive) se interpreta como UTC. Un formato inválido
    lanza `ValueError`.
    """
    corte = datetime.fromisoformat(valor)
    if corte.tzinfo is None:
        return corte.replace(tzinfo=timezone.utc)
    return corte.astimezone(timezone.utc)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Script CLI de purgado seguro de telemetría y logs expirados en Datamaq Telemetry "
            "(Cumplimiento ISO 27001 A.8.10 y minimización de datos). "
            "Recomendado para ejecución en cron diario a las 03:00 UTC."
        )
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Días de retención para sobreescribir globalmente todas las políticas (ej. 7 o 30).",
    )
    parser.add_argument(
        "--days-instantaneas",
        type=int,
        default=None,
        help="Días de retención para telemetría instantánea cruda (default: 45 días).",
    )
    parser.add_argument(
        "--days-energy",
        type=int,
        default=None,
        help="Días de retención para telemetría acumulada (default: 1825 días / 5 años).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50000,
        help="Tamaño de lote para borrados por transacción (default: 50000).",
    )
    parser.add_argument(
        "--hasta",
        type=str,
        default=None,
        help="Corte temporal explícito en UTC (ej. '2026-09-01 21:40:04'); purga todo lo anterior.",
    )
    args = parser.parse_args()

    logger = get_logger("cli_purge")
    print("[*] Iniciando proceso de purgado de telemetría...")

    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo_telem = MySQLTelemetriaRepository(db)
        use_case = PurgarTelemetriaExpiradaUseCase(repo_telem, logger=logger)

        req_dto = PurgaRequestDTO(
            dias_retencion_override=args.days,
            dias_retencion_instantaneas=args.days_instantaneas,
            dias_retencion_energia=args.days_energy,
            corte_hasta=parsear_corte_hasta(args.hasta) if args.hasta else None,
            batch_size=args.batch_size,
        )
        res = use_case.ejecutar(req_dto)

        print("[+] Proceso de purga finalizado exitosamente:")
        print(f"    - Instantáneas eliminadas: {res.instantaneas_eliminadas}")
        print(f"    - Energías eliminadas: {res.energias_eliminadas}")
        print(f"    - Status logs eliminados: {res.status_logs_eliminados}")
        print(f"    - Alertas resueltas eliminadas: {res.alertas_resueltas_eliminadas}")
        print(f"    - Total registros eliminados: {res.total_registros_eliminados}")
        print(f"    - Duración: {res.duracion_segundos} segundos")
    except Exception as e:
        print(f"[!] Error ejecutando la purga: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
