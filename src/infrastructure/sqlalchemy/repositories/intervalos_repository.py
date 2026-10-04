"""src/infrastructure/sqlalchemy/repositories/intervalos_repository.py."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from src.domain.maquinas.entities import IntervaloActividadMáquina
from src.domain.maquinas.ports import RepositorioIntervalosActividadPort
from src.domain.maquinas.value_objects import OrigenClasificacionCarga
from src.infrastructure.sqlalchemy.models_cargas import LoadActivityIntervalModel


def _a_float(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _a_decimal(valor: float | None) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None else None


class MySQLIntervalosActividadRepository(RepositorioIntervalosActividadPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: LoadActivityIntervalModel) -> IntervaloActividadMáquina:
        return IntervaloActividadMáquina(
            id=model.id,
            dispositivo_id=model.device_id,
            carga_id=model.load_id,
            inicio_at=model.start_at,
            fin_at=model.end_at,
            potencia_media_w=_a_float(model.avg_power_w),
            delta_reactiva_var=_a_float(model.delta_reactive_var),
            energia_kwh=_a_float(model.energy_kwh),
            confianza=_a_float(model.confidence),
            origen=OrigenClasificacionCarga(model.origin),
            corregido_por_usuario_id=model.corrected_by_user_id,
            corregido_at=model.corrected_at,
            notas=model.notes,
        )

    def _aplicar(self, model: LoadActivityIntervalModel, intervalo: IntervaloActividadMáquina) -> None:
        model.load_id = intervalo.carga_id
        model.avg_power_w = _a_decimal(intervalo.potencia_media_w)
        model.delta_reactive_var = _a_decimal(intervalo.delta_reactiva_var)
        model.energy_kwh = _a_decimal(intervalo.energia_kwh)
        model.confidence = _a_decimal(intervalo.confianza)
        model.origin = intervalo.origen.value
        model.corrected_by_user_id = intervalo.corregido_por_usuario_id
        model.corrected_at = intervalo.corregido_at
        model.notes = intervalo.notas

    def obtener_por_id(self, intervalo_id: int) -> IntervaloActividadMáquina | None:
        model = self.db.query(LoadActivityIntervalModel).filter(LoadActivityIntervalModel.id == intervalo_id).first()
        return self._to_entity(model) if model else None

    def listar_por_dispositivo(
        self, dispositivo_id: str, desde: datetime, hasta: datetime
    ) -> list[IntervaloActividadMáquina]:
        modelos = (
            self.db.query(LoadActivityIntervalModel)
            .filter(
                LoadActivityIntervalModel.device_id == dispositivo_id,
                LoadActivityIntervalModel.start_at >= desde,
                LoadActivityIntervalModel.start_at <= hasta,
            )
            .order_by(asc(LoadActivityIntervalModel.start_at))
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def listar_por_carga(self, carga_id: str, limite: int = 100) -> list[IntervaloActividadMáquina]:
        modelos = (
            self.db.query(LoadActivityIntervalModel)
            .filter(LoadActivityIntervalModel.load_id == carga_id)
            .order_by(desc(LoadActivityIntervalModel.start_at))
            .limit(limite)
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def guardar(self, intervalo: IntervaloActividadMáquina) -> IntervaloActividadMáquina:
        model = None
        if intervalo.id is not None:
            model = (
                self.db.query(LoadActivityIntervalModel).filter(LoadActivityIntervalModel.id == intervalo.id).first()
            )
        if model is None:
            model = LoadActivityIntervalModel(
                device_id=intervalo.dispositivo_id,
                start_at=intervalo.inicio_at,
                end_at=intervalo.fin_at,
            )
            self.db.add(model)

        self._aplicar(model, intervalo)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def reemplazar_ventana(
        self,
        dispositivo_id: str,
        desde: datetime,
        hasta: datetime,
        intervalos: list[IntervaloActividadMáquina],
    ) -> int:
        """Reescribe la ventana preservando lo que corrigió una persona.

        Las filas con origen `CORRECCION_HUMANA` no se borran ni se pisan, y además se
        excluye del alta cualquier intervalo cuya ventana temporal ya esté ocupada por
        una de ellas: reprocesar no puede deshacer una corrección.
        """
        existentes = (
            self.db.query(LoadActivityIntervalModel)
            .filter(
                LoadActivityIntervalModel.device_id == dispositivo_id,
                LoadActivityIntervalModel.start_at >= desde,
                LoadActivityIntervalModel.start_at <= hasta,
            )
            .all()
        )
        protegidas = {
            (m.start_at, m.end_at) for m in existentes if m.origin == OrigenClasificacionCarga.CORRECCION_HUMANA.value
        }
        for model in existentes:
            if (model.start_at, model.end_at) not in protegidas:
                self.db.delete(model)
        self.db.flush()

        escritos = 0
        for intervalo in intervalos:
            if (intervalo.inicio_at, intervalo.fin_at) in protegidas:
                continue
            model = LoadActivityIntervalModel(
                device_id=intervalo.dispositivo_id,
                start_at=intervalo.inicio_at,
                end_at=intervalo.fin_at,
            )
            self._aplicar(model, intervalo)
            self.db.add(model)
            escritos += 1

        self.db.commit()
        return escritos
