"""src/infrastructure/yaml/verificador_unifilar.py — valida el unifilar declarado en el YAML al arrancar."""

import structlog

from src.domain.telemetria.exceptions import EstructuraUnifilarInvalidaError
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = structlog.get_logger("yaml.integrity")


def verificar_unifilar_plantas(yaml_repo: YamlOrganizacionesRepository | None = None) -> dict[str, int]:
    """Corre `ArbolUnifilarService.validar()` sobre cada planta del YAML.

    La estructura ya no se escribe por API (no hay `PUT /unifilar`), así que el
    único momento en que un árbol inválido puede entrar es un commit al YAML.
    Advierte, no bloquea: un YAML roto en producción debe verse en el log, no
    tirar el servicio.
    """
    if yaml_repo is None:
        yaml_repo = YamlOrganizacionesRepository()

    plantas = yaml_repo.listar_plantas()
    invalidas = 0
    for planta in plantas:
        nodos = yaml_repo.obtener_nodos_unifilar(planta.id)
        try:
            ArbolUnifilarService(nodos).validar()
        except EstructuraUnifilarInvalidaError as e:
            invalidas += 1
            logger.warning("unifilar_yaml_invalido", planta_id=planta.id, planta=planta.nombre, error=str(e))

    if invalidas:
        logger.warning("verificacion_unifilar_con_advertencias", plantas=len(plantas), invalidas=invalidas)
    else:
        logger.info("verificacion_unifilar_exitosa", plantas=len(plantas))
    return {"plantas": len(plantas), "invalidas": invalidas}
