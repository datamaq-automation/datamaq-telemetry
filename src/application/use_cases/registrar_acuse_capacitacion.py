"""src/application/use_cases/registrar_acuse_capacitacion.py."""

import uuid
from datetime import datetime, timezone

from src.domain.sge.entities import RegistroCapacitacionSge
from src.domain.sge.exceptions import (
    ArticuloSgeNoEncontradoError,
    CapacitacionNoAutorizadaParaRolError,
    CapacitacionYaRegistradaError,
)
from src.domain.sge.ports import (
    RepositorioDocumentacionSgePort,
    RepositorioRegistroCapacitacionesSgePort,
)


class RegistrarAcuseCapacitacionUseCase:
    """Caso de uso para registrar evidencia de capacitación y toma de conciencia (ISO 50001 §7.2 / §7.3)."""

    def __init__(
        self,
        repo_documentacion: RepositorioDocumentacionSgePort,
        repo_capacitaciones: RepositorioRegistroCapacitacionesSgePort,
    ):
        self._repo_documentacion = repo_documentacion
        self._repo_capacitaciones = repo_capacitaciones

    def ejecutar(
        self,
        usuario_id: str,
        articulo_id: str,
        rol_usuario: str,
        version_doc: str,
        comentarios: str | None = None,
    ) -> RegistroCapacitacionSge:
        articulo = self._repo_documentacion.obtener_por_id(articulo_id)
        if articulo is None:
            raise ArticuloSgeNoEncontradoError(f"El artículo '{articulo_id}' no existe.")

        if not articulo.es_visible_para(rol_usuario):
            raise CapacitacionNoAutorizadaParaRolError(
                f"El rol '{rol_usuario}' no está autorizado para la capacitación '{articulo_id}'."
            )

        existente = self._repo_capacitaciones.obtener_por_usuario_y_articulo(usuario_id, articulo_id)
        if existente is not None:
            raise CapacitacionYaRegistradaError(
                f"El usuario '{usuario_id}' ya registró la capacitación '{articulo_id}'."
            )

        registro = RegistroCapacitacionSge(
            id=str(uuid.uuid4()),
            usuario_id=usuario_id,
            articulo_id=articulo_id,
            rol_usuario=rol_usuario,
            fecha_completado=datetime.now(timezone.utc),
            version_doc=version_doc,
            comentarios=comentarios,
        )
        self._repo_capacitaciones.registrar(registro)
        return registro
