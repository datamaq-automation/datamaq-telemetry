"""src/application/use_cases/consultar_historico_facturas.py — Histórico de facturas de la distribuidora."""

from src.application.dtos.sge_dto import FacturaDistribuidoraResponseDTO
from src.application.mappers.sge_mapper import factura_to_dto
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class ConsultarHistoricoFacturasUseCase:
    def __init__(self, repo_organizaciones: RepositorioOrganizacionesPort) -> None:
        self._repo_org = repo_organizaciones

    def ejecutar(self, planta_id: str) -> list[FacturaDistribuidoraResponseDTO]:
        planta = self._repo_org.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada.")

        facturas = self._repo_org.obtener_facturas_planta(planta_id)
        return [factura_to_dto(f) for f in facturas]
