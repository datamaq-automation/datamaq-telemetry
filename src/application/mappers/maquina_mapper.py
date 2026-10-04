"""src/application/mappers/carga_mapper.py."""

from src.application.dtos.carga_dto import (
    EnsayoResponseDTO,
    MáquinaCreateDTO,
    MáquinaResponseDTO,
    FirmaMáquinaDTO,
    IntervaloActividadResponseDTO,
    ResultadoCalibracionDTO,
)
from src.domain.maquinas.entities import (
    CampanaCaracterizacion,
    Carga,
    IntervaloActividadCarga,
)
from src.domain.maquinas.value_objects import FirmaCarga, ResultadoCalibracion


class MáquinaMapper:
    @staticmethod
    def firma_to_dto(firma: FirmaCarga | None) -> FirmaMáquinaDTO | None:
        if firma is None:
            return None
        return FirmaMáquinaDTO(
            potencia_w=firma.potencia_w,
            dispersion_w=firma.dispersion_w,
            potencia_reactiva_var=firma.potencia_reactiva_var,
            factor_potencia=firma.factor_potencia,
            duracion_encendido_s=firma.duracion_encendido_s,
            duracion_encendido_mad_s=firma.duracion_encendido_mad_s,
            duracion_apagado_s=firma.duracion_apagado_s,
            pico_arranque_w=firma.pico_arranque_w,
            origen=firma.origen,
            muestras=firma.muestras,
            medida_en=firma.medida_en,
            es_resistiva=firma.es_resistiva,
            esta_completa=firma.esta_completa,
        )

    @staticmethod
    def to_dto(entity: Carga) -> MáquinaResponseDTO:
        return MáquinaResponseDTO(
            id=entity.id,
            dispositivo_id=entity.dispositivo_id,
            nombre=entity.nombre,
            categoria=entity.categoria,
            naturaleza_electrica=entity.naturaleza_electrica,
            patron_operacion=entity.patron_operacion,
            potencia_nominal_w=entity.potencia_nominal_w,
            potencia_esperada_w=entity.potencia_esperada_w,
            firma=MáquinaMapper.firma_to_dto(entity.firma),
            esta_caracterizada=entity.esta_caracterizada,
            activa=entity.activa,
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
        )

    @staticmethod
    def create_dto_to_entity(dto: MáquinaCreateDTO, id_str: str) -> Carga:
        return Carga(
            id=id_str,
            dispositivo_id=dto.dispositivo_id,
            nombre=dto.nombre,
            categoria=dto.categoria,
            naturaleza_electrica=dto.naturaleza_electrica,
            potencia_nominal_w=dto.potencia_nominal_w,
        )


class CampanaMapper:
    @staticmethod
    def resultado_to_dto(resultado: ResultadoCalibracion | None) -> ResultadoCalibracionDTO | None:
        if resultado is None:
            return None
        return ResultadoCalibracionDTO(
            estado=resultado.estado,
            motivo=resultado.motivo,
            detalle=resultado.detalle,
            linea_base_W=resultado.linea_base_w,
            linea_base_VAR=resultado.linea_base_var,
            muestras_analizadas=resultado.muestras_analizadas,
            muestras_en_regimen=resultado.muestras_en_regimen,
            dispersion_relativa=resultado.dispersion_relativa,
            cadencia_mediana_s=resultado.cadencia_mediana_s,
            firma=MáquinaMapper.firma_to_dto(resultado.firma),
        )

    @staticmethod
    def to_dto(
        entity: CampanaCaracterizacion,
        resultado: ResultadoCalibracion | None = None,
        rafaga_solicitada: bool | None = None,
    ) -> EnsayoResponseDTO:
        return EnsayoResponseDTO(
            id=entity.id,
            dispositivo_id=entity.dispositivo_id,
            carga_id=entity.carga_id,
            tipo=entity.tipo,
            estado=entity.estado,
            inicio_at=entity.inicio_at,
            fin_planificado_at=entity.fin_planificado_at,
            fin_at=entity.fin_at,
            duracion_planificada_s=entity.duracion_planificada_s,
            linea_base_W=entity.linea_base_w,
            linea_base_VAR=entity.linea_base_var,
            muestras=entity.muestras,
            motivo_descarte=entity.motivo_descarte,
            notas=entity.notas,
            rafaga_solicitada=rafaga_solicitada,
            resultado=CampanaMapper.resultado_to_dto(resultado),
        )


class IntervaloActividadMapper:
    @staticmethod
    def to_dto(entity: IntervaloActividadCarga) -> IntervaloActividadResponseDTO:
        return IntervaloActividadResponseDTO(
            id=entity.id,
            dispositivo_id=entity.dispositivo_id,
            carga_id=entity.carga_id,
            inicio_at=entity.inicio_at,
            fin_at=entity.fin_at,
            duracion_segundos=entity.duracion_segundos,
            potencia_media_W=entity.potencia_media_w,
            delta_reactiva_VAR=entity.delta_reactiva_var,
            energia_kwh=entity.energia_kwh,
            confianza=entity.confianza,
            origen=entity.origen,
            esta_atribuido=entity.esta_atribuido,
            corregido_por_usuario_id=entity.corregido_por_usuario_id,
            corregido_at=entity.corregido_at,
            notas=entity.notas,
        )
