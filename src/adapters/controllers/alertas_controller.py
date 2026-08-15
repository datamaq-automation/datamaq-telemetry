from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase


class AlertasController:
    def __init__(self, use_case: GestionarAlertasUseCase):
        self.use_case = use_case

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        limite: int = 100,
    ) -> list[AlertaResponseDTO]:
        return self.use_case.listar_alertas(
            dispositivo_id=dispositivo_id,
            solo_abiertas=solo_abiertas,
            limite=limite,
        )

    def resolver_alerta(self, alerta_id: int) -> AlertaResponseDTO:
        return self.use_case.resolver_alerta(alerta_id)
