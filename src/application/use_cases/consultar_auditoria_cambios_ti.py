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
    ) -> list[dict[str, Any]]:
        """Cambios más recientes primero, con los filtros opcionales."""
        return self._repositorio.listar(
            dispositivo_id=dispositivo_id,
            tipo_cambio=tipo_cambio,
            desde=desde,
            hasta=hasta,
        )

    def detalle(self, cambio_id: int) -> dict[str, Any] | None:
        """Registro completo de un cambio, o None si no existe."""
        return self._repositorio.obtener(cambio_id)
