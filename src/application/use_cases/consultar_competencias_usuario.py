"""src/application/use_cases/consultar_competencias_usuario.py."""

from dataclasses import dataclass

from src.domain.sge.entities import ArticuloSge, RegistroCapacitacionSge
from src.domain.sge.ports import (
    RepositorioDocumentacionSgePort,
    RepositorioRegistroCapacitacionesSgePort,
)


@dataclass(frozen=True)
class EstadoCompetenciasUsuario:
    """Consolidado de cumplimiento de competencias y capacitaciones de un usuario."""

    usuario_id: str
    rol_usuario: str
    capacitaciones_completadas: tuple[RegistroCapacitacionSge, ...]
    capacitaciones_pendientes: tuple[ArticuloSge, ...]
    porcentaje_cumplimiento: float


class ConsultarCompetenciasUsuarioUseCase:
    """Caso de uso para evaluar el estado de competencias de un usuario (ISO 50001 §7.2)."""

    def __init__(
        self,
        repo_documentacion: RepositorioDocumentacionSgePort,
        repo_capacitaciones: RepositorioRegistroCapacitacionesSgePort,
    ):
        self._repo_documentacion = repo_documentacion
        self._repo_capacitaciones = repo_capacitaciones

    def ejecutar(self, usuario_id: str, rol_usuario: str) -> EstadoCompetenciasUsuario:
        articulos_rol = self._repo_documentacion.listar_por_rol(rol_usuario)
        completadas = self._repo_capacitaciones.listar_por_usuario(usuario_id)
        ids_completados = {c.articulo_id for c in completadas}

        pendientes = [a for a in articulos_rol if a.id not in ids_completados]
        total_requeridas = len(articulos_rol)

        if total_requeridas > 0:
            completadas_rol = ids_completados.intersection({a.id for a in articulos_rol})
            porcentaje = round((len(completadas_rol) / total_requeridas) * 100.0, 1)
        else:
            porcentaje = 100.0

        return EstadoCompetenciasUsuario(
            usuario_id=usuario_id,
            rol_usuario=rol_usuario,
            capacitaciones_completadas=tuple(completadas),
            capacitaciones_pendientes=tuple(pendientes),
            porcentaje_cumplimiento=porcentaje,
        )
