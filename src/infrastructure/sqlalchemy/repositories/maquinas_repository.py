"""src/infrastructure/sqlalchemy/repositories/cargas_repository.py."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import asc, func
from sqlalchemy.orm import Session

from src.domain.maquinas.entities import Máquina
from src.domain.maquinas.ports import RepositorioMáquinasPort, RepositorioSeriePotenciaPort
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal
from src.infrastructure.sqlalchemy.models import (
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)
from src.infrastructure.sqlalchemy.models_maquinas import LoadModel


def _a_float(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _a_decimal(valor: float | None) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None else None


class MySQLMáquinasRepository(RepositorioMáquinasPort):
    """Persistencia del catálogo de cargas.

    La firma se guarda aplanada en columnas de `loads` en vez de en una tabla propia:
    cada carga tiene una sola firma vigente, y el rastro de cómo se obtuvo vive en las
    campañas de caracterización.
    """

    def __init__(self, db: Session):
        self.db = db

    def _firma_de_modelo(self, model: LoadModel) -> FirmaCarga | None:
        if model.signature_power_w is None:
            return None
        return FirmaCarga(
            potencia_w=float(model.signature_power_w),
            dispersion_w=float(model.signature_dispersion_w or 0),
            potencia_reactiva_var=_a_float(model.signature_reactive_var),
            factor_potencia=_a_float(model.signature_power_factor),
            duracion_encendido_s=_a_float(model.signature_on_seconds),
            duracion_encendido_mad_s=_a_float(model.signature_on_mad_seconds),
            duracion_apagado_s=_a_float(model.signature_off_seconds),
            pico_arranque_w=_a_float(model.signature_startup_peak_w),
            origen=OrigenFirma(model.signature_source) if model.signature_source else OrigenFirma.CHAPA,
            muestras=model.signature_samples or 0,
            medida_en=model.signature_measured_at,
        )

    def _to_entity(self, model: LoadModel) -> Máquina:
        return Máquina(
            id=model.id,
            dispositivo_id=model.device_id,
            nombre=model.name,
            categoria=CategoriaCarga(model.category),
            naturaleza_electrica=NaturalezaElectrica(model.electrical_nature),
            patron_operacion=PatronOperacion(model.operation_pattern),
            potencia_nominal_w=_a_float(model.nameplate_power_w),
            firma=self._firma_de_modelo(model),
            activa=model.is_active,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def _aplicar(self, model: LoadModel, maquina: Máquina) -> None:
        model.name = maquina.nombre
        model.category = maquina.categoria.value
        model.electrical_nature = maquina.naturaleza_electrica.value
        model.operation_pattern = maquina.patron_operacion.value
        model.nameplate_power_w = _a_decimal(maquina.potencia_nominal_w)
        model.is_active = maquina.activa

        firma = maquina.firma
        model.signature_power_w = _a_decimal(firma.potencia_w) if firma else None
        model.signature_dispersion_w = _a_decimal(firma.dispersion_w) if firma else None
        model.signature_reactive_var = _a_decimal(firma.potencia_reactiva_var) if firma else None
        model.signature_power_factor = _a_decimal(firma.factor_potencia) if firma else None
        model.signature_on_seconds = _a_decimal(firma.duracion_encendido_s) if firma else None
        model.signature_on_mad_seconds = _a_decimal(firma.duracion_encendido_mad_s) if firma else None
        model.signature_off_seconds = _a_decimal(firma.duracion_apagado_s) if firma else None
        model.signature_startup_peak_w = _a_decimal(firma.pico_arranque_w) if firma else None
        model.signature_source = firma.origen.value if firma else None
        model.signature_samples = firma.muestras if firma else None
        model.signature_measured_at = firma.medida_en if firma else None

    def obtener_por_id(self, maquina_id: str) -> Máquina | None:
        model = self.db.query(LoadModel).filter(LoadModel.id == maquina_id).first()
        return self._to_entity(model) if model else None

    def obtener_por_nombre(self, dispositivo_id: str, nombre: str) -> Máquina | None:
        model = self.db.query(LoadModel).filter(LoadModel.device_id == dispositivo_id, LoadModel.name == nombre).first()
        return self._to_entity(model) if model else None

    def listar_por_dispositivo(self, dispositivo_id: str, solo_activas: bool = False) -> list[Máquina]:
        q = self.db.query(LoadModel).filter(LoadModel.device_id == dispositivo_id)
        if solo_activas:
            q = q.filter(LoadModel.is_active.is_(True))
        return [self._to_entity(m) for m in q.order_by(LoadModel.name).all()]

    def listar(self) -> list[Máquina]:
        return [self._to_entity(m) for m in self.db.query(LoadModel).order_by(LoadModel.name).all()]

    def guardar(self, carga: Máquina) -> Máquina:
        model = self.db.query(LoadModel).filter(LoadModel.id == carga.id).first()
        if not model:
            model = LoadModel(id=carga.id, device_id=carga.dispositivo_id)
            self._aplicar(model, carga)
            self.db.add(model)
        else:
            self._aplicar(model, carga)

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)


class MySQLSeriePotenciaRepository(RepositorioSeriePotenciaPort):
    """Query columnar sobre `telemetry_instantaneous` para el análisis de cargas.

    Proyecta cuatro columnas en vez de la fila entera y ordena por tiempo ascendente,
    porque todos los servicios del contexto asumen la serie en orden cronológico.
    Solo trae filas con potencia activa: una lectura sin P no aporta nada a un análisis
    de potencia y arrastrarla obligaría a cada servicio a filtrarla de nuevo.
    """

    def __init__(self, db: Session):
        self.db = db

    def listar_serie_potencia(
        self,
        dispositivo_id: str,
        desde: datetime,
        hasta: datetime | None = None,
        limite: int | None = None,
    ) -> list[LecturaPotenciaTemporal]:
        q = self.db.query(
            TelemetryInstantaneousModel.recorded_at,
            TelemetryInstantaneousModel.total_active_power,
            TelemetryInstantaneousModel.total_reactive_power,
            TelemetryInstantaneousModel.total_power_factor,
        ).filter(
            TelemetryInstantaneousModel.device_id == dispositivo_id,
            TelemetryInstantaneousModel.recorded_at >= desde,
            TelemetryInstantaneousModel.total_active_power.isnot(None),
            TelemetryInstantaneousModel.es_dato_confiable.is_(True),
        )
        if hasta is not None:
            q = q.filter(TelemetryInstantaneousModel.recorded_at <= hasta)
        q = q.order_by(asc(TelemetryInstantaneousModel.recorded_at))
        if limite is not None:
            q = q.limit(limite)

        return [
            LecturaPotenciaTemporal(
                momento=fila[0],
                potencia_w=float(fila[1]),
                potencia_reactiva_var=_a_float(fila[2]),
                factor_potencia=_a_float(fila[3]),
            )
            for fila in q.all()
        ]

    def obtener_energia_consumida_kwh(self, dispositivo_id: str, desde: datetime, hasta: datetime) -> float | None:
        """Diferencia entre el último y el primer valor del contador en la ventana.

        El contador es monótono creciente, así que la resta es el consumo exacto del
        período. Devuelve `None` si no hay al menos dos lecturas: con una sola no hay
        diferencia que calcular, y devolver 0 se confundiría con "no consumió nada".
        """
        extremos = (
            self.db.query(
                func.min(TelemetryEnergyModel.net_active_energy_kwh),
                func.max(TelemetryEnergyModel.net_active_energy_kwh),
                func.count(TelemetryEnergyModel.id),
            )
            .filter(
                TelemetryEnergyModel.device_id == dispositivo_id,
                TelemetryEnergyModel.recorded_at >= desde,
                TelemetryEnergyModel.recorded_at <= hasta,
                TelemetryEnergyModel.net_active_energy_kwh.isnot(None),
            )
            .one()
        )
        minimo, maximo, cantidad = extremos
        if cantidad < 2 or minimo is None or maximo is None:
            return None
        return round(float(maximo) - float(minimo), 4)
