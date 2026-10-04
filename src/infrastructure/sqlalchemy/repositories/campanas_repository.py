"""src/infrastructure/sqlalchemy/repositories/campanas_repository.py."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.cargas.entities import CampanaCaracterizacion
from src.domain.cargas.ports import RepositorioCampanasPort
from src.domain.cargas.value_objects import (
    EstadoCampana,
    MotivoDescarte,
    MuestraCampana,
    TipoCampana,
)
from src.infrastructure.sqlalchemy.models_cargas import (
    CampaignSampleModel,
    CharacterizationCampaignModel,
)


def _a_float(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _a_decimal(valor: float | None) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None else None


class MySQLCampanasRepository(RepositorioCampanasPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: CharacterizationCampaignModel) -> CampanaCaracterizacion:
        return CampanaCaracterizacion(
            id=model.id,
            dispositivo_id=model.device_id,
            carga_id=model.load_id,
            tipo=TipoCampana(model.campaign_type),
            estado=EstadoCampana(model.state),
            inicio_at=model.start_at,
            fin_planificado_at=model.planned_end_at,
            fin_at=model.end_at,
            linea_base_w=_a_float(model.baseline_w),
            linea_base_var=_a_float(model.baseline_var),
            muestras=model.sample_count,
            motivo_descarte=MotivoDescarte(model.discard_reason) if model.discard_reason else None,
            notas=model.notes,
            creado_por_usuario_id=model.created_by_user_id,
            creado_en=model.created_at,
        )

    def obtener_por_id(self, campana_id: str) -> CampanaCaracterizacion | None:
        model = (
            self.db.query(CharacterizationCampaignModel).filter(CharacterizationCampaignModel.id == campana_id).first()
        )
        return self._to_entity(model) if model else None

    def obtener_en_curso_por_dispositivo(self, dispositivo_id: str) -> CampanaCaracterizacion | None:
        model = (
            self.db.query(CharacterizationCampaignModel)
            .filter(
                CharacterizationCampaignModel.device_id == dispositivo_id,
                CharacterizationCampaignModel.state == EstadoCampana.EN_CURSO.value,
            )
            .order_by(desc(CharacterizationCampaignModel.start_at))
            .first()
        )
        return self._to_entity(model) if model else None

    def listar_en_curso(self) -> list[CampanaCaracterizacion]:
        modelos = (
            self.db.query(CharacterizationCampaignModel)
            .filter(CharacterizationCampaignModel.state == EstadoCampana.EN_CURSO.value)
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def listar_por_carga(self, carga_id: str) -> list[CampanaCaracterizacion]:
        modelos = (
            self.db.query(CharacterizationCampaignModel)
            .filter(CharacterizationCampaignModel.load_id == carga_id)
            .order_by(desc(CharacterizationCampaignModel.start_at))
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def guardar(self, campana: CampanaCaracterizacion) -> CampanaCaracterizacion:
        model = (
            self.db.query(CharacterizationCampaignModel).filter(CharacterizationCampaignModel.id == campana.id).first()
        )
        if not model:
            model = CharacterizationCampaignModel(
                id=campana.id,
                device_id=campana.dispositivo_id,
                load_id=campana.carga_id,
                campaign_type=campana.tipo.value,
                start_at=campana.inicio_at,
                planned_end_at=campana.fin_planificado_at,
                created_by_user_id=campana.creado_por_usuario_id,
            )
            self.db.add(model)

        model.state = campana.estado.value
        model.end_at = campana.fin_at
        model.baseline_w = _a_decimal(campana.linea_base_w)
        model.baseline_var = _a_decimal(campana.linea_base_var)
        model.sample_count = campana.muestras
        model.discard_reason = campana.motivo_descarte.value if campana.motivo_descarte else None
        model.notes = campana.notas

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def _ya_existe_muestra(self, campana_id: str, momento: datetime) -> bool:
        return (
            self.db.query(CampaignSampleModel.id)
            .filter(
                CampaignSampleModel.campaign_id == campana_id,
                CampaignSampleModel.recorded_at == momento,
            )
            .first()
            is not None
        )

    def agregar_muestra(self, campana_id: str, muestra: MuestraCampana) -> bool:
        """`False` si la muestra ya estaba: es un redelivery de MQTT, no un error.

        La unicidad se delega a la restricción de la tabla en vez de consultarla antes:
        acá se escribe una fila por segundo y un SELECT previo por cada una duplicaría
        el trabajo sin cerrar la carrera de todos modos.

        Ante un `IntegrityError` se verifica que la fila realmente esté, y si no está se
        vuelve a lanzar. Tragarse toda la familia de errores de integridad haría que una
        falla sistemática (una FK rota, una columna que no acepta el valor) se reportara
        como "duplicado" y la campaña terminara vacía sin que nadie se enterara.
        """
        model = CampaignSampleModel(
            campaign_id=campana_id,
            recorded_at=muestra.momento,
            active_power_w=_a_decimal(muestra.potencia_w),
            reactive_power_var=_a_decimal(muestra.potencia_reactiva_var),
            apparent_power_va=_a_decimal(muestra.potencia_aparente_va),
            power_factor=_a_decimal(muestra.factor_potencia),
            voltage_v=_a_decimal(muestra.tension_v),
            current_a=_a_decimal(muestra.corriente_a),
        )
        try:
            self.db.add(model)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if self._ya_existe_muestra(campana_id, muestra.momento):
                return False
            raise

        self.db.query(CharacterizationCampaignModel).filter(CharacterizationCampaignModel.id == campana_id).update(
            {CharacterizationCampaignModel.sample_count: CharacterizationCampaignModel.sample_count + 1}
        )
        self.db.commit()
        return True

    def listar_muestras(self, campana_id: str) -> list[MuestraCampana]:
        filas = (
            self.db.query(
                CampaignSampleModel.recorded_at,
                CampaignSampleModel.active_power_w,
                CampaignSampleModel.reactive_power_var,
                CampaignSampleModel.apparent_power_va,
                CampaignSampleModel.power_factor,
                CampaignSampleModel.voltage_v,
                CampaignSampleModel.current_a,
            )
            .filter(
                CampaignSampleModel.campaign_id == campana_id,
                CampaignSampleModel.active_power_w.isnot(None),
            )
            .order_by(asc(CampaignSampleModel.recorded_at))
            .all()
        )
        return [
            MuestraCampana(
                momento=f[0],
                potencia_w=float(f[1]),
                potencia_reactiva_var=_a_float(f[2]),
                potencia_aparente_va=_a_float(f[3]),
                factor_potencia=_a_float(f[4]),
                tension_v=_a_float(f[5]),
                corriente_a=_a_float(f[6]),
            )
            for f in filas
        ]
