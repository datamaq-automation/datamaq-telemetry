import structlog
from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.models import UserModel
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = structlog.get_logger("database.integrity")


def verificar_consistencia_organizaciones(
    db: Session, yaml_repo: YamlOrganizacionesRepository | None = None
) -> dict[str, int]:
    """Verifica que todas las organization_id referenciadas en usuarios existan en el YAML de organizaciones.

    Devuelve un diccionario con métricas de la verificación.
    """
    if yaml_repo is None:
        yaml_repo = YamlOrganizacionesRepository()

    organizaciones_yaml = yaml_repo.listar_organizaciones()
    ids_yaml_validos = {org.id for org in organizaciones_yaml}

    usuarios = db.query(UserModel).filter(UserModel.organization_id.isnot(None)).all()
    huerfanos_count = 0

    for usuario in usuarios:
        if usuario.organization_id not in ids_yaml_validos:
            huerfanos_count += 1
            logger.warning(
                "usuario_organizacion_huerfana_detectada",
                usuario_id=usuario.id,
                username=usuario.username,
                organizacion_id_inexistente=usuario.organization_id,
            )

    if huerfanos_count > 0:
        logger.warning(
            "verificacion_consistencia_organizaciones_con_advertencias",
            total_usuarios_con_org=len(usuarios),
            usuarios_huerfanos=huerfanos_count,
            orgs_validas_yaml=len(ids_yaml_validos),
        )
    else:
        logger.info(
            "verificacion_consistencia_organizaciones_exitosa",
            total_usuarios_con_org=len(usuarios),
            orgs_validas_yaml=len(ids_yaml_validos),
        )

    return {
        "total_usuarios_con_org": len(usuarios),
        "usuarios_huerfanos": huerfanos_count,
        "orgs_validas_yaml": len(ids_yaml_validos),
    }
