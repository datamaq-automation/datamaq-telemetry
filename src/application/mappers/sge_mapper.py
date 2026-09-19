"""src/application/mappers/sge_mapper.py."""

from src.application.dtos.sge_dto import (
    EstadoCompetenciasUsuarioDTO,
    RegistroCapacitacionResponseDTO,
    SgeDocArticleDTO,
)
from src.application.use_cases.consultar_competencias_usuario import (
    EstadoCompetenciasUsuario,
)
from src.domain.sge.entities import ArticuloSge, RegistroCapacitacionSge


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


def registro_to_dto(registro: RegistroCapacitacionSge) -> RegistroCapacitacionResponseDTO:
    """Convierte una entidad RegistroCapacitacionSge a RegistroCapacitacionResponseDTO."""
    return RegistroCapacitacionResponseDTO(
        id=registro.id,
        usuarioId=registro.usuario_id,
        articuloId=registro.articulo_id,
        rolUsuario=registro.rol_usuario,
        fechaCompletado=registro.fecha_completado.isoformat(),
        versionDoc=registro.version_doc,
        comentarios=registro.comentarios,
    )


def estado_to_dto(estado: EstadoCompetenciasUsuario) -> EstadoCompetenciasUsuarioDTO:
    """Convierte EstadoCompetenciasUsuario a EstadoCompetenciasUsuarioDTO."""
    return EstadoCompetenciasUsuarioDTO(
        usuarioId=estado.usuario_id,
        rolUsuario=estado.rol_usuario,
        capacitacionesCompletadas=[registro_to_dto(r) for r in estado.capacitaciones_completadas],
        capacitacionesPendientes=[articulo_to_dto(a) for a in estado.capacitaciones_pendientes],
        porcentajeCumplimiento=estado.porcentaje_cumplimiento,
    )
