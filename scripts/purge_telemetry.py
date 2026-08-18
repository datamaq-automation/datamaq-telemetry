import argparse
import os
import sys

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLTelemetriaRepository


def main():
    parser = argparse.ArgumentParser(
        description="Script CLI de purgado seguro de telemetría y logs expirados en Datamaq Telemetry."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Días de retención para sobreescribir la política por defecto (ej. 7 o 30).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Tamaño de lote para borrados por transacción (default: 1000).",
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
