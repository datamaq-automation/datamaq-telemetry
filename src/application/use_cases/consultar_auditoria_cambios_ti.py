"""src/application/use_cases/consultar_auditoria_cambios_ti.py."""

from datetime import datetime
from typing import Any

from src.domain.telemetria.ports import RepositorioAuditoriaCambiosTIPort


class ConsultarAuditoriaCambiosTIUseCase:
    """Lectura de la auditoría de cambios de TI para los endpoints de administración."""

    def __init__(self, repositorio: RepositorioAuditoriaCambiosTIPort) -> None:
        self._repositorio = repositorio

    def listar(
        self,
        dispositivo_id: str | None = None,
        tipo_cambio: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        *,
        organizacion_id: str | None = None,
        todas_las_organizaciones: bool = False,
    ) -> list[dict[str, Any]]:
        """Cambios más recientes primero, con los filtros opcionales.

        Sin ``todas_las_organizaciones`` hace falta una organización: sin ella no hay nada que listar (datamaq#128).
        """
        if not todas_las_organizaciones and not organizacion_id:
            return []
        return self._repositorio.listar(
            dispositivo_id=dispositivo_id,
            tipo_cambio=tipo_cambio,
            desde=desde,
            hasta=hasta,
            organizacion_id=None if todas_las_organizaciones else organizacion_id,
        )

    def detalle(
        self,
        cambio_id: int,
        *,
        organizacion_id: str | None = None,
        todas_las_organizaciones: bool = False,
    ) -> dict[str, Any] | None:
        """Registro completo de un cambio, o None si no existe o no es de la organización."""
        if not todas_las_organizaciones and not organizacion_id:
            return None
        return self._repositorio.obtener(cambio_id, None if todas_las_organizaciones else organizacion_id)
