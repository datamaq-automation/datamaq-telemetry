import uuid
from datetime import datetime, timedelta, timezone

from src.application.dtos.maquina_dto import (
    HistogramaPotenciaResponseDTO,
    MaquinaCreateDTO,
    MaquinaResponseDTO,
    MaquinaUpdateDTO,
)
from src.application.mappers.maquina_mapper import MaquinaMapper
from src.domain.disponibilidad.exceptions import (
    DispositivoYaAsociadoAMaquinaError,
    MaquinaNoEncontradaError,
)
from src.domain.disponibilidad.ports import RepositorioMaquinasPort
from src.domain.disponibilidad.services import CalibradorUmbralService
from src.domain.telemetria.ports import RepositorioTelemetriaPort


class GestionarMaquinasUseCase:
    def __init__(
        self,
        repo_maquinas: RepositorioMaquinasPort,
        repo_telemetria: RepositorioTelemetriaPort,
    ):
        self.repo_maquinas = repo_maquinas
        self.repo_telemetria = repo_telemetria

    def listar_maquinas(self) -> list[MaquinaResponseDTO]:
        return [MaquinaMapper.to_dto(m) for m in self.repo_maquinas.listar()]

    def obtener_maquina(self, maquina_id: str) -> MaquinaResponseDTO:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")
        return MaquinaMapper.to_dto(maquina)

    def registrar_maquina(self, dto: MaquinaCreateDTO) -> MaquinaResponseDTO:
        existente = self.repo_maquinas.obtener_por_dispositivo_id(dto.dispositivo_id)
        if existente:
            raise DispositivoYaAsociadoAMaquinaError(
                f"El dispositivo '{dto.dispositivo_id}' ya está asociado a la máquina '{existente.id}'."
            )
        entity = MaquinaMapper.create_dto_to_entity(dto, str(uuid.uuid4()))
        saved = self.repo_maquinas.guardar(entity)
        return MaquinaMapper.to_dto(saved)

    def actualizar_maquina(self, maquina_id: str, dto: MaquinaUpdateDTO) -> MaquinaResponseDTO:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")

        if dto.nombre is not None:
            maquina.nombre = dto.nombre
        if dto.umbral_marcha_w is not None:
            maquina.umbral_marcha_w = dto.umbral_marcha_w
        if dto.ventana_persistencia_lecturas is not None:
            maquina.ventana_persistencia_lecturas = dto.ventana_persistencia_lecturas
        if dto.ventana_persistencia_segundos is not None:
            maquina.ventana_persistencia_segundos = dto.ventana_persistencia_segundos

        saved = self.repo_maquinas.guardar(maquina)
        return MaquinaMapper.to_dto(saved)

    def calcular_histograma(self, maquina_id: str, dias: int = 7) -> HistogramaPotenciaResponseDTO:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")

        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        lecturas_w = self.repo_telemetria.listar_potencias_para_histograma(maquina.dispositivo_id, desde)

        bordes, frecuencias = CalibradorUmbralService.construir_histograma(lecturas_w)
        umbral_sugerido = CalibradorUmbralService.calcular_umbral(lecturas_w)

        return HistogramaPotenciaResponseDTO(
            dispositivo_id=maquina.dispositivo_id,
            dias_analizados=dias,
            cantidad_lecturas=len(lecturas_w),
            bordes_bins_w=bordes,
            frecuencias=frecuencias,
            umbral_sugerido_w=umbral_sugerido,
        )
