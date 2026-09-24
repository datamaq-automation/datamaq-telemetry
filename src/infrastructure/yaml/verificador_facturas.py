"""src/infrastructure/yaml/verificador_facturas.py — valida el histórico de facturas al arrancar."""

import re

import structlog

from src.domain.sge.entities import FacturaDistribuidora
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = structlog.get_logger("yaml.integrity")

_PATRON_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _magnitudes_negativas(f: FacturaDistribuidora) -> list[str]:
    campos = {
        "energia_activa_punta_kwh": f.energia_activa_punta_kwh,
        "energia_activa_resto_kwh": f.energia_activa_resto_kwh,
        "energia_activa_valle_kwh": f.energia_activa_valle_kwh,
        "potencia_contratada_punta_kw": f.potencia_contratada_punta_kw,
        "potencia_contratada_fuera_punta_kw": f.potencia_contratada_fuera_punta_kw,
        "potencia_adquirida_punta_kw": f.potencia_adquirida_punta_kw,
        "potencia_adquirida_fuera_punta_kw": f.potencia_adquirida_fuera_punta_kw,
        "importe_potencia_ars": f.importe_potencia_ars,
        "importe_energia_ars": f.importe_energia_ars,
        "importe_total_ars": f.importe_total_ars,
    }
    return [nombre for nombre, valor in campos.items() if valor is not None and valor < 0.0]


def verificar_facturas_plantas(yaml_repo: YamlOrganizacionesRepository | None = None) -> dict[str, int]:
    """Valida el histórico de facturas (`data/facturas_distribuidora.yml`) de cada planta.

    Distinta invariante que `verificador_unifilar.py` (árbol de nodos): acá es una lista
    plana histórica, así que se valida la unicidad de (período, tipo_dato) por planta —no
    "período único", porque potencia y energía pueden venir de proveedores distintos en dos
    documentos separados del mismo período (ver `FacturaDistribuidora` en `domain/sge/entities.py`)—,
    formato `YYYY-MM` y magnitudes no negativas. Advierte, no bloquea: igual criterio que el
    resto de los validadores de integridad YAML.
    """
    if yaml_repo is None:
        yaml_repo = YamlOrganizacionesRepository()

    plantas = yaml_repo.listar_plantas()
    invalidas = 0
    for planta in plantas:
        facturas = yaml_repo.obtener_facturas_planta(planta.id)
        documentos_vistos: set[tuple[str, str]] = set()
        for factura in facturas:
            errores: list[str] = []
            if not _PATRON_PERIODO.match(factura.periodo):
                errores.append(f"período '{factura.periodo}' no tiene formato YYYY-MM")
            clave_documento = (factura.periodo, factura.tipo_dato)
            if clave_documento in documentos_vistos:
                errores.append(f"período '{factura.periodo}' tipo '{factura.tipo_dato}' duplicado en la planta")
            documentos_vistos.add(clave_documento)
            negativas = _magnitudes_negativas(factura)
            if negativas:
                errores.append(f"magnitudes negativas: {', '.join(negativas)}")

            if errores:
                invalidas += 1
                logger.warning(
                    "factura_yaml_invalida",
                    planta_id=planta.id,
                    planta=planta.nombre,
                    periodo=factura.periodo,
                    errores=errores,
                )

    if invalidas:
        logger.warning("verificacion_facturas_con_advertencias", plantas=len(plantas), invalidas=invalidas)
    else:
        logger.info("verificacion_facturas_exitosa", plantas=len(plantas))
    return {"plantas": len(plantas), "invalidas": invalidas}
