"""src/infrastructure/yaml/verificador_slugs_planta.py — valida unicidad de slugs de planta al arrancar."""

from collections import Counter

import structlog

from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = structlog.get_logger("yaml.integrity")


def verificar_slugs_planta(yaml_repo: YamlOrganizacionesRepository | None = None) -> dict[str, int]:
    """Verifica que el slug de planta sea único por organización (decisión 2026-09-25).

    Planta es dato maestro del YAML, sin tabla en MySQL: no hay constraint de DB posible,
    así que la unicidad se verifica acá, con el mismo patrón "advierte, no bloquea" que
    `verificador_unifilar.py`.
    """
    if yaml_repo is None:
        yaml_repo = YamlOrganizacionesRepository()
    plantas = yaml_repo.listar_plantas()
    colisiones = 0
    por_organizacion: dict[str, Counter] = {}
    for planta in plantas:
        contador = por_organizacion.setdefault(planta.organizacion_id, Counter())
        contador[planta.slug] += 1
    for organizacion_id, contador in por_organizacion.items():
        for slug, cantidad in contador.items():
            if cantidad > 1:
                colisiones += 1
                logger.warning(
                    "slug_planta_duplicado",
                    organizacion_id=organizacion_id,
                    slug=slug,
                    cantidad=cantidad,
                )
    if colisiones:
        logger.warning("verificacion_slugs_planta_con_advertencias", plantas=len(plantas), colisiones=colisiones)
    else:
        logger.info("verificacion_slugs_planta_exitosa", plantas=len(plantas))
    return {"plantas": len(plantas), "colisiones": colisiones}
