"""src/application/use_cases/gestionar_planes.py."""

import uuid

from src.application.dtos.plan_dto import PlanCreateDTO, PlanResponseDTO
from src.application.mappers.plan_mapper import PlanMapper
from src.domain.telemetria.ports import RepositorioPlanesPort
from src.domain.telemetria.value_objects import VisibilidadPlan


class GestionarPlanesUseCase:
    def __init__(self, repo_planes: RepositorioPlanesPort) -> None:
        self.repo_planes = repo_planes

    def listar_catalogo(self, solo_publicos: bool = False) -> list[PlanResponseDTO]:
        planes = self.repo_planes.listar_planes()
        if solo_publicos:
            planes = [p for p in planes if p.visibilidad == VisibilidadPlan.PUBLICO]
        return [PlanMapper.to_dto(p) for p in planes]

    def crear_plan(self, dto: PlanCreateDTO) -> PlanResponseDTO:
        entity = PlanMapper.create_dto_to_entity(dto, str(uuid.uuid4()))
        guardado = self.repo_planes.guardar_plan(entity)
        return PlanMapper.to_dto(guardado)
