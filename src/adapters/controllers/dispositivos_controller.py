from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.application.dtos.organizacion_dto import (
    OrganizacionCreateDTO,
    OrganizacionResponseDTO,
    PlantaCreateDTO,
    PlantaResponseDTO,
)
from src.application.use_cases.gestionar_dispositivos import (
    GestionarDispositivosUseCase,
)


class DispositivosController:
    def __init__(self, use_case: GestionarDispositivosUseCase):
        self.use_case = use_case

    def listar_dispositivos(self, planta_id: str | None = None) -> list[DispositivoResponseDTO]:
        return self.use_case.listar_dispositivos(planta_id)

    def obtener_dispositivo(self, id_o_uid: str) -> DispositivoResponseDTO:
        return self.use_case.obtener_dispositivo(id_o_uid)

    def registrar_dispositivo(self, dto: DispositivoCreateDTO) -> DispositivoResponseDTO:
        return self.use_case.registrar_dispositivo(dto)

    def actualizar_dispositivo(self, id_o_uid: str, dto: DispositivoUpdateDTO) -> DispositivoResponseDTO:
        return self.use_case.actualizar_dispositivo(id_o_uid, dto)

    def listar_organizaciones(self) -> list[OrganizacionResponseDTO]:
        return self.use_case.listar_organizaciones()

    def crear_organizacion(self, dto: OrganizacionCreateDTO) -> OrganizacionResponseDTO:
        return self.use_case.crear_organizacion(dto)

    def listar_plantas(self, organizacion_id: str | None = None) -> list[PlantaResponseDTO]:
        return self.use_case.listar_plantas(organizacion_id)

    def crear_planta(self, dto: PlantaCreateDTO) -> PlantaResponseDTO:
        return self.use_case.crear_planta(dto)
