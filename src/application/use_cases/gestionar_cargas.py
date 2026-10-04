"""src/application/use_cases/gestionar_cargas.py."""

import uuid
from datetime import datetime, timezone

from src.application.dtos.carga_dto import (
    CargaCreateDTO,
    CargaResponseDTO,
    CargaUpdateDTO,
    FirmaManualRequestDTO,
)
from src.application.mappers.maquina_mapper import MáquinaMapper
from src.domain.maquinas.entities import Máquina
from src.domain.maquinas.exceptions import (
    CargaDuplicadaError,
    CargaNoEncontradaError,
    FirmaCargaInvalidaError,
)
from src.domain.maquinas.ports import RepositorioMáquinasPort
from src.domain.maquinas.value_objects import FirmaCarga, OrigenFirma


class GestionarCargasUseCase:
    """CRUD del catálogo de cargas detrás de un medidor agregado.

    Es la puerta de entrada del conocimiento del proceso: qué hay conectado. El doc
    conceptual de disponibilidad (§6.3) insiste en que ese conocimiento se *inyecta*
    como restricción de diseño y no se espera que la estadística lo descubra sola —
    este catálogo es esa inyección.
    """

    def __init__(self, repo_cargas: RepositorioMáquinasPort):
        self.repo_cargas = repo_cargas

    def _obtener_o_fallar(self, carga_id: str) -> Carga:
        carga = self.repo_cargas.obtener_por_id(carga_id)
        if not carga:
            raise CargaNoEncontradaError(f"Carga '{carga_id}' no encontrada.")
        return carga

    def listar_cargas(self, dispositivo_id: str | None = None, solo_activas: bool = False) -> list[CargaResponseDTO]:
        if dispositivo_id is None:
            cargas = self.repo_cargas.listar()
            if solo_activas:
                cargas = [c for c in cargas if c.activa]
        else:
            cargas = self.repo_cargas.listar_por_dispositivo(dispositivo_id, solo_activas=solo_activas)
        return [MáquinaMapper.to_dto(c) for c in cargas]

    def obtener_carga(self, carga_id: str) -> CargaResponseDTO:
        return MáquinaMapper.to_dto(self._obtener_o_fallar(carga_id))

    def registrar_carga(self, dto: CargaCreateDTO) -> CargaResponseDTO:
        existente = self.repo_cargas.obtener_por_nombre(dto.dispositivo_id, dto.nombre)
        if existente:
            raise CargaDuplicadaError(
                f"El dispositivo '{dto.dispositivo_id}' ya tiene una carga llamada '{dto.nombre}'."
            )
        entity = MáquinaMapper.create_dto_to_entity(dto, str(uuid.uuid4()))
        return MáquinaMapper.to_dto(self.repo_cargas.guardar(entity))

    def actualizar_carga(self, carga_id: str, dto: CargaUpdateDTO) -> CargaResponseDTO:
        carga = self._obtener_o_fallar(carga_id)

        if dto.nombre is not None and dto.nombre != carga.nombre:
            colision = self.repo_cargas.obtener_por_nombre(carga.dispositivo_id, dto.nombre)
            if colision is not None and colision.id != carga.id:
                raise CargaDuplicadaError(
                    f"El dispositivo '{carga.dispositivo_id}' ya tiene una carga llamada '{dto.nombre}'."
                )
            carga.nombre = dto.nombre
        if dto.categoria is not None:
            carga.categoria = dto.categoria
        if dto.naturaleza_electrica is not None:
            carga.naturaleza_electrica = dto.naturaleza_electrica
        if dto.patron_operacion is not None:
            carga.patron_operacion = dto.patron_operacion
        if dto.potencia_nominal_w is not None:
            carga.potencia_nominal_w = dto.potencia_nominal_w
        if dto.activa is not None:
            carga.activa = dto.activa

        return MáquinaMapper.to_dto(self.repo_cargas.guardar(carga))

    def fijar_firma_manual(self, carga_id: str, dto: FirmaManualRequestDTO) -> CargaResponseDTO:
        """Calibración manual, el escape para cuando no hay campaña posible.

        La firma queda marcada `CHAPA` a propósito: no fue medida sobre el equipo, así
        que el motor de atribución debe confiar menos en ella que en una de campaña.
        """
        carga = self._obtener_o_fallar(carga_id)
        if dto.dispersion_w > dto.potencia_w:
            raise FirmaCargaInvalidaError(
                "La dispersión no puede superar a la potencia: describiría una carga que apaga y prende sola."
            )

        carga.firma = FirmaCarga(
            potencia_w=dto.potencia_w,
            dispersion_w=dto.dispersion_w,
            potencia_reactiva_var=dto.potencia_reactiva_var,
            factor_potencia=dto.factor_potencia,
            duracion_encendido_s=dto.duracion_encendido_s,
            duracion_apagado_s=dto.duracion_apagado_s,
            origen=OrigenFirma.CHAPA,
            muestras=0,
            medida_en=datetime.now(timezone.utc),
        )
        return MáquinaMapper.to_dto(self.repo_cargas.guardar(carga))
