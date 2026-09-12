"""src/application/mappers/sge_mapper.py."""

from src.application.dtos.sge_dto import SgeDocArticleDTO
from src.domain.sge.entities import ArticuloSge


def articulo_to_dto(articulo: ArticuloSge) -> SgeDocArticleDTO:
    """Convierte una entidad de dominio ArticuloSge a SgeDocArticleDTO."""
    return SgeDocArticleDTO(
        id=articulo.id,
        titulo=articulo.titulo,
        categoria=articulo.categoria,
        rolesPermitidos=list(articulo.roles_permitidos),
        resumen=articulo.resumen,
        puntosClave=list(articulo.puntos_clave),
        accionesInmediatas=list(articulo.acciones_inmediatas),
        referenciaIso=articulo.referencia_iso,
        documentoUrl=articulo.documento_url,
    )
