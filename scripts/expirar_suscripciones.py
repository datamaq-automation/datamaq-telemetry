import argparse
import os
import sys
from datetime import datetime, timezone

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.repositories.planes_repository import MySQLPlanesRepository
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository


def parsear_ahora(valor: str) -> datetime:
    """Convierte un string ISO en un datetime UTC *aware*, para pruebas manuales del corte.

    Un valor sin offset (naive) se interpreta como UTC. Un formato inválido lanza `ValueError`.
    """
    ahora = datetime.fromisoformat(valor)
    if ahora.tzinfo is None:
        return ahora.replace(tzinfo=timezone.utc)
    return ahora.astimezone(timezone.utc)


def main():
    parser = argparse.ArgumentParser(
        description="Baja a modo_free las organizaciones cuya suscripción PRO ya venció "
        "(pro_vence_en < ahora), respetando el período de gracia ya aplicado por el "
        "proveedor de pago antes de dejar vencer la fecha."
    )
    parser.add_argument(
        "--ahora",
        type=str,
        default=None,
        help="Corte temporal explícito en UTC (ej. '2026-09-01 21:40:04'), para pruebas manuales.",
    )
    args = parser.parse_args()
    logger = get_logger("cli_expirar_suscripciones")
    print("[*] Iniciando expiración de suscripciones vencidas...")
    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo_suscripciones = MySQLSuscripcionesRepository(db)
        repo_planes = MySQLPlanesRepository(db)
        use_case = GestionarSuscripcionesUseCase(repo_suscripciones, repo_planes)

        ahora = parsear_ahora(args.ahora) if args.ahora else None
        afectadas = use_case.expirar_vencidas(ahora)

        print(f"[+] Proceso de expiración finalizado: {len(afectadas)} organización(es) bajadas a modo_free.")
        for s in afectadas:
            logger.info("suscripcion_expirada", organizacion_id=s.organizacion_id)
            print(f"    - {s.organizacion_id}")
    except Exception as e:
        print(f"[!] Error ejecutando la expiración de suscripciones: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
