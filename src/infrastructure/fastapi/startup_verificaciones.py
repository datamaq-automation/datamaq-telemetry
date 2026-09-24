"""src/infrastructure/fastapi/startup_verificaciones.py — validadores de integridad YAML al arrancar.

Extraído de `server.py` (que tiene el límite de 500 líneas de CONVENTIONS.md) para no repetir el
patrón "advierte, no bloquea" inline por cada validador nuevo.
"""

import structlog

logger = structlog.get_logger(__name__)


def ejecutar_verificaciones_yaml() -> None:
    """Corre los validadores de integridad de `data/*.yml`. Cada uno advierte, no bloquea
    el arranque: un YAML roto en producción debe verse en el log, no tirar el servicio."""
    try:
        from src.infrastructure.yaml.verificador_unifilar import verificar_unifilar_plantas

        verificar_unifilar_plantas()
    except Exception as e:
        logger.warning("verificacion_unifilar_fallida", error=str(e))

    try:
        from src.infrastructure.yaml.verificador_facturas import verificar_facturas_plantas

        verificar_facturas_plantas()
    except Exception as e:
        logger.warning("verificacion_facturas_fallida", error=str(e))
