import uuid

from src.application.dtos.grupo_dispositivos_dto import (
    GrupoDispositivosCreateDTO,
    GrupoDispositivosResponseDTO,
)
from src.domain.telemetria.entities import GrupoDispositivos
from src.domain.telemetria.exceptions import (
    DispositivoDePlantaDistintaError,
    DispositivoNoEncontradoError,
    GrupoDispositivosNoEncontradoError,
    LimiteGruposExcedidoError,
)
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioGruposDispositivosPort,
)

MAX_GRUPOS_POR_PLANTA = 20


class GestionarGruposDispositivosUseCase:
    def __init__(
        self,
        repo_grupos: RepositorioGruposDispositivosPort,
        repo_dispositivos: RepositorioDispositivosPort,
    ):
        self.repo_grupos = repo_grupos
        self.repo_dispositivos = repo_dispositivos

    def _grupo_to_dto(self, grupo: GrupoDispositivos) -> GrupoDispositivosResponseDTO:
        return GrupoDispositivosResponseDTO(
            id=grupo.id,
            planta_id=grupo.planta_id,
            nombre=grupo.nombre,
            dispositivos_ids=grupo.dispositivos_ids,
            creado_en=grupo.creado_en,
            actualizado_en=grupo.actualizado_en,
        )

    def _validar_dispositivo_en_planta(self, dispositivo_id: str, planta_id: str) -> None:
        dispositivo = self.repo_dispositivos.obtener_por_id(dispositivo_id)
        if dispositivo is None:
            raise DispositivoNoEncontradoError(dispositivo_id)
        if dispositivo.planta_id != planta_id:
            raise DispositivoDePlantaDistintaError(
                f"El dispositivo {dispositivo_id} no pertenece a la planta {planta_id}"
            )

    def _validar_cupo_grupos(self, planta_id: str) -> None:
        actual = len(self.repo_grupos.listar_por_planta(planta_id))
        if actual >= MAX_GRUPOS_POR_PLANTA:
            raise LimiteGruposExcedidoError(
                f"La planta {planta_id} alcanzó el límite de {MAX_GRUPOS_POR_PLANTA} grupos de dispositivos."
            )

    def crear_grupo(self, dto: GrupoDispositivosCreateDTO) -> GrupoDispositivosResponseDTO:
        self._validar_cupo_grupos(dto.planta_id)
        for dispositivo_id in dto.dispositivos_ids:
            self._validar_dispositivo_en_planta(dispositivo_id, dto.planta_id)

        grupo = GrupoDispositivos(
            id=str(uuid.uuid4()),
            planta_id=dto.planta_id,
            nombre=dto.nombre,
            dispositivos_ids=dto.dispositivos_ids,
        )
        creado = self.repo_grupos.crear(grupo)
        return self._grupo_to_dto(creado)

    def listar_grupos(self, planta_id: str) -> list[GrupoDispositivosResponseDTO]:
        grupos = self.repo_grupos.listar_por_planta(planta_id)
        return [self._grupo_to_dto(g) for g in grupos]

    def obtener_grupo(self, grupo_id: str) -> GrupoDispositivosResponseDTO:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)
        return self._grupo_to_dto(grupo)

    def agregar_miembro(self, grupo_id: str, dispositivo_id: str) -> GrupoDispositivosResponseDTO:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)
        self._validar_dispositivo_en_planta(dispositivo_id, grupo.planta_id)
        self.repo_grupos.agregar_miembro(grupo_id, dispositivo_id)
        return self.obtener_grupo(grupo_id)

    def quitar_miembro(self, grupo_id: str, dispositivo_id: str) -> GrupoDispositivosResponseDTO:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)
        self.repo_grupos.quitar_miembro(grupo_id, dispositivo_id)
        return self.obtener_grupo(grupo_id)

    def eliminar_grupo(self, grupo_id: str) -> None:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)
        self.repo_grupos.eliminar(grupo_id)
