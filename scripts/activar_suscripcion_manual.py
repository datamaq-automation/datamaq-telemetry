import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.domain.telemetria.exceptions import PlanNoEncontradoError
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.repositories.planes_repository import MySQLPlanesRepository
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def main():
    parser = argparse.ArgumentParser(
        description="Activa o extiende manualmente la suscripción de una organización, sin pasar "
        "por Mercado Pago. Puente operativo para cobrar por transferencia/link simple mientras "
        "las credenciales de MP no estén configuradas, o para altas de cortesía/prueba. "
        "La organización debe existir ya en data/organizaciones.yml."
    )
    parser.add_argument("--org-nombre", required=True, help="Nombre exacto de la organización en el YAML.")
    parser.add_argument("--plan-id", required=True, help="id del plan (ver GET /api/v1/planes).")
    parser.add_argument(
        "--dias", type=int, default=30, help="Días de vigencia a partir de ahora (default: 30, un mes)."
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Sin este flag, el script solo muestra qué haría (dry-run) y no escribe nada.",
    )
    args = parser.parse_args()

    logger = get_logger("cli_activar_suscripcion_manual")
    repo_org = YamlOrganizacionesRepository()
    org = next((o for o in repo_org.listar_organizaciones() if o.nombre == args.org_nombre), None)
    if org is None:
        print(
            f"[!] La organización '{args.org_nombre}' no está en data/organizaciones.yml. "
            "Declarala ahí antes de activar su suscripción.",
            file=sys.stderr,
        )
        sys.exit(1)

    hasta = datetime.now(timezone.utc) + timedelta(days=args.dias)
    print(f"[*] Organización: {org.nombre} (id={org.id})")
    print(f"[*] Plan: {args.plan_id}")
    print(f"[*] Vigente hasta: {hasta.isoformat()} ({args.dias} días desde ahora)")

    if not args.confirmar:
        print("[i] Dry-run: no se escribió nada. Repetí el comando con --confirmar para aplicar.")
        return

    session_factory = get_session_factory()
    db = session_factory()
    try:
        use_case = GestionarSuscripcionesUseCase(MySQLSuscripcionesRepository(db), MySQLPlanesRepository(db))
        suscripcion = use_case.activar_o_extender(org.id, args.plan_id, hasta)
        logger.info(
            "suscripcion_activada_manualmente",
            organizacion_id=org.id,
            plan_id=args.plan_id,
            pro_vence_en=suscripcion.pro_vence_en.isoformat() if suscripcion.pro_vence_en else None,
        )
        print(f"[+] Suscripción activada: {org.nombre} queda PRO hasta {hasta.isoformat()}.")
    except PlanNoEncontradoError as e:
        print(f"[!] {e.mensaje}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
