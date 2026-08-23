from fastapi import HTTPException
from src.application.dtos.unifilar_topologia_dto import UnifilarTopologiaDTO
from src.application.use_cases.consultar_unifilar_topologia import ConsultarUnifilarTopologiaUseCase
from src.domain.telemetria.exceptions import PlantaNoEncontradaError


class UnifilarTopologiaController:
    def __init__(self, use_case: ConsultarUnifilarTopologiaUseCase):
        self.use_case = use_case

    def obtener_topologia(self, planta_id: str) -> UnifilarTopologiaDTO:
        try:
            return self.use_case.ejecutar(planta_id)
        except PlantaNoEncontradaError as e:
            # Relanzar para que el router la maneje como HTTP 404
            raise HTTPException(status_code=404, detail=str(e)) from e
