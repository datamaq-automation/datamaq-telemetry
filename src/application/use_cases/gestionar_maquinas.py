import uuid
from datetime import datetime, timedelta, timezone

from src.application.dtos.maquina_dto import (
    DiagnosticoConfianzaModalDTO,
    DiagnosticoEstacionariedadDTO,
    HistogramaPotenciaResponseDTO,
    MaquinaCreateDTO,
    MaquinaResponseDTO,
    MaquinaUpdateDTO,
    RegimenOperacionDTO,
)
from src.application.mappers.maquina_mapper import MaquinaMapper
from src.domain.disponibilidad.exceptions import (
    DispositivoYaAsociadoAMaquinaError,
    MaquinaNoEncontradaError,
)
from src.domain.disponibilidad.ports import RepositorioMaquinasPort
from src.domain.disponibilidad.services import SegmentadorRegimenesService
from src.domain.telemetria.ports import RepositorioTelemetriaPort


class GestionarMaquinasUseCase:
    LIMITE_LECTURAS_HISTOGRAMA = 100_000

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

    def calcular_histograma(
        self,
        maquina_id: str,
        dias: int = 7,
        limite: int | None = None,
    ) -> HistogramaPotenciaResponseDTO:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")

        limite_efectivo = limite if limite is not None else self.LIMITE_LECTURAS_HISTOGRAMA
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        lecturas = self.repo_telemetria.listar_potencias_para_histograma(
            maquina.dispositivo_id, desde, limite=limite_efectivo
        )

        segmentacion = SegmentadorRegimenesService.analizar_serie(lecturas)
        lecturas_truncadas = len(lecturas) >= limite_efectivo

        regimenes_dto = [
            RegimenOperacionDTO(
                indice=r.indice,
                potencia_tipica_w=r.potencia_tipica_w,
                limite_inferior_w=r.limite_inferior_w,
                limite_superior_w=r.limite_superior_w,
                masa=r.masa,
                mediana_w=r.mediana_w,
                mad_w=r.mad_w,
                persistencia=r.persistencia,
                variacion_mediana_w_s=r.variacion_mediana_w_s,
                naturaleza=r.naturaleza,
            )
            for r in segmentacion.regimenes
        ]

        diagnostico_modal = None
        if segmentacion.diagnostico_modal is not None:
            diagnostico_modal = DiagnosticoConfianzaModalDTO(
                num_modas_estable=segmentacion.diagnostico_modal.num_modas_estable,
                fraccion_ventanas_consistentes=segmentacion.diagnostico_modal.fraccion_ventanas_consistentes,
                es_multimodal_confiable=segmentacion.diagnostico_modal.es_multimodal_confiable,
            )

        diagnostico_estacionariedad = None
        if segmentacion.diagnostico_estacionariedad is not None:
            diagnostico_estacionariedad = DiagnosticoEstacionariedadDTO(
                num_subventanas=segmentacion.diagnostico_estacionariedad.num_subventanas,
                desplazamiento_maximo_w=segmentacion.diagnostico_estacionariedad.desplazamiento_maximo_w,
                desplazamiento_maximo_relativo=segmentacion.diagnostico_estacionariedad.desplazamiento_maximo_relativo,
                es_estacionario=segmentacion.diagnostico_estacionariedad.es_estacionario,
            )

        return HistogramaPotenciaResponseDTO(
            dispositivo_id=maquina.dispositivo_id,
            dias_analizados=dias,
            cantidad_lecturas=len(lecturas),
            bordes_bins_w=segmentacion.bordes_bins_w,
            frecuencias=segmentacion.frecuencias,
            umbral_sugerido_w=segmentacion.umbral_marcha_sugerido_w,
            escala=segmentacion.escala,
            epsilon_w=segmentacion.epsilon_w,
            lecturas_truncadas=lecturas_truncadas,
            lecturas_descartadas=segmentacion.lecturas_no_positivas,
            regimenes=regimenes_dto,
            diagnostico_modal=diagnostico_modal,
            diagnostico_estacionariedad=diagnostico_estacionariedad,
        )
