"""src/application/mappers/sge_mapper.py."""

from src.application.dtos.sge_dto import (
    EstadoCompetenciasUsuarioDTO,
    FacturaDistribuidoraResponseDTO,
    RegistroCapacitacionResponseDTO,
    SgeDocArticleDTO,
)
from src.application.use_cases.consultar_competencias_usuario import (
    EstadoCompetenciasUsuario,
)
from src.domain.sge.entities import ArticuloSge, FacturaDistribuidora, RegistroCapacitacionSge


def factura_to_dto(f: FacturaDistribuidora) -> FacturaDistribuidoraResponseDTO:
    """Convierte una entidad FacturaDistribuidora a FacturaDistribuidoraResponseDTO."""
    return FacturaDistribuidoraResponseDTO(
        id=f.id,
        planta_id=f.planta_id,
        periodo=f.periodo,
        distribuidora=f.distribuidora,
        numero_factura=f.numero_factura,
        tarifa=f.tarifa,
        dias_facturados=f.dias_facturados,
        energia_activa_punta_kwh=f.energia_activa_punta_kwh,
        energia_activa_resto_kwh=f.energia_activa_resto_kwh,
        energia_activa_valle_kwh=f.energia_activa_valle_kwh,
        energia_facturada_kwh=f.energia_facturada_kwh,
        potencia_contratada_punta_kw=f.potencia_contratada_punta_kw,
        potencia_contratada_fuera_punta_kw=f.potencia_contratada_fuera_punta_kw,
        potencia_adquirida_punta_kw=f.potencia_adquirida_punta_kw,
        potencia_adquirida_fuera_punta_kw=f.potencia_adquirida_fuera_punta_kw,
        potencia_excedida_punta_kw=f.potencia_excedida_punta_kw,
        potencia_excedida_fuera_punta_kw=f.potencia_excedida_fuera_punta_kw,
        importe_potencia_ars=f.importe_potencia_ars,
        importe_energia_ars=f.importe_energia_ars,
        importe_total_ars=f.importe_total_ars,
        valor_energia_ars_kwh_promedio=f.valor_energia_ars_kwh_promedio,
    )


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
