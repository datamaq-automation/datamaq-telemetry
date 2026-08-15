from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase


class PurgaController:
    def __init__(self, use_case: PurgarTelemetriaExpiradaUseCase):
        self.use_case = use_case

    def ejecutar_purga(self, dto: PurgaRequestDTO) -> PurgaResultadoDTO:
        return self.use_case.ejecutar(dto)
