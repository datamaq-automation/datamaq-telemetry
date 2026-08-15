from src.application.dtos.plan_dto import PlanCreateDTO, PlanResponseDTO
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase


class PlanesController:
    def __init__(self, use_case: GestionarPlanesUseCase):
        self.use_case = use_case

    def listar_planes(self, solo_publicos: bool = False) -> list[PlanResponseDTO]:
        return self.use_case.listar_catalogo(solo_publicos=solo_publicos)

    def crear_plan(self, dto: PlanCreateDTO) -> PlanResponseDTO:
        return self.use_case.crear_plan(dto)
