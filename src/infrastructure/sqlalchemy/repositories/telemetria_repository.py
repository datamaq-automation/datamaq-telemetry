"""src/infrastructure/sqlalchemy/repositories/telemetria_repository.py."""

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

from sqlalchemy import asc, desc, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session, aliased

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
)
from src.domain.telemetria.ports import RepositorioTelemetriaPort
from src.domain.telemetria.servicios.harmonics_thd import ThdFase
from src.domain.telemetria.value_objects import (
    LecturaPotenciaTemporal,
)
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceModel,
    DeviceStatusLogModel,
    FacilityModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)
from src.infrastructure.sqlalchemy.repositories.telemetria_conteos_purga import ConteosPurgaSqlMixin
from src.infrastructure.sqlalchemy.repositories.telemetria_mappers import (
    alerta_a_modelo,
    alerta_to_entity,
    energia_to_entity,
    instantanea_to_entity,
)
from src.infrastructure.sqlalchemy.repositories.telemetria_thd_actualizador import (
    actualizar_thd_en_ultima_instantanea,
)


class MySQLTelemetriaRepository(ConteosPurgaSqlMixin, RepositorioTelemetriaPort):
    _instantanea_to_entity = staticmethod(instantanea_to_entity)
    _energia_to_entity = staticmethod(energia_to_entity)
    _alerta_to_entity = staticmethod(alerta_to_entity)

    def __init__(self, db: Session):
        self.db = db
        self._zonas_tz_verificadas: set[str] = set()  # Una sonda de CONVERT_TZ por zona y request (#14).

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        model = TelemetryInstantaneousModel(
            device_id=lectura.dispositivo_id,
            recorded_at=lectura.registrado_en,
            voltage_r=lectura.fase_r.tension.voltios if lectura.fase_r.tension else None,
            current_r=lectura.fase_r.corriente.amperios if lectura.fase_r.corriente else None,
            active_power_r=lectura.fase_r.potencia_activa.vatios if lectura.fase_r.potencia_activa else None,
            reactive_power_r=lectura.fase_r.potencia_reactiva.var if lectura.fase_r.potencia_reactiva else None,
            apparent_power_r=lectura.fase_r.potencia_aparente.va if lectura.fase_r.potencia_aparente else None,
            power_factor_r=lectura.fase_r.factor_potencia.valor if lectura.fase_r.factor_potencia else None,
            thd_v_r=Decimal(str(lectura.fase_r.thd_v_porcentaje))
            if lectura.fase_r.thd_v_porcentaje is not None
            else None,
            thd_i_r=Decimal(str(lectura.fase_r.thd_i_porcentaje))
            if lectura.fase_r.thd_i_porcentaje is not None
            else None,
            voltage_s=lectura.fase_s.tension.voltios if lectura.fase_s.tension else None,
            current_s=lectura.fase_s.corriente.amperios if lectura.fase_s.corriente else None,
            active_power_s=lectura.fase_s.potencia_activa.vatios if lectura.fase_s.potencia_activa else None,
            reactive_power_s=lectura.fase_s.potencia_reactiva.var if lectura.fase_s.potencia_reactiva else None,
            apparent_power_s=lectura.fase_s.potencia_aparente.va if lectura.fase_s.potencia_aparente else None,
            power_factor_s=lectura.fase_s.factor_potencia.valor if lectura.fase_s.factor_potencia else None,
            thd_v_s=Decimal(str(lectura.fase_s.thd_v_porcentaje))
            if lectura.fase_s.thd_v_porcentaje is not None
            else None,
            thd_i_s=Decimal(str(lectura.fase_s.thd_i_porcentaje))
            if lectura.fase_s.thd_i_porcentaje is not None
            else None,
            voltage_t=lectura.fase_t.tension.voltios if lectura.fase_t.tension else None,
            current_t=lectura.fase_t.corriente.amperios if lectura.fase_t.corriente else None,
            active_power_t=lectura.fase_t.potencia_activa.vatios if lectura.fase_t.potencia_activa else None,
            reactive_power_t=lectura.fase_t.potencia_reactiva.var if lectura.fase_t.potencia_reactiva else None,
            apparent_power_t=lectura.fase_t.potencia_aparente.va if lectura.fase_t.potencia_aparente else None,
            power_factor_t=lectura.fase_t.factor_potencia.valor if lectura.fase_t.factor_potencia else None,
            thd_v_t=Decimal(str(lectura.fase_t.thd_v_porcentaje))
            if lectura.fase_t.thd_v_porcentaje is not None
            else None,
            thd_i_t=Decimal(str(lectura.fase_t.thd_i_porcentaje))
            if lectura.fase_t.thd_i_porcentaje is not None
            else None,
            total_active_power=lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None,
            total_reactive_power=lectura.potencia_reactiva_total.var if lectura.potencia_reactiva_total else None,
            total_apparent_power=lectura.potencia_aparente_total.va if lectura.potencia_aparente_total else None,
            total_power_factor=lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None,
            desbalance_tension_porcentaje=lectura.desbalance_tension_porcentaje,
            current_n=lectura.corriente_neutro_estimada.amperios if lectura.corriente_neutro_estimada else None,
            voltage_linea_V=lectura.voltage_linea_V,
            tension_neutro_estimada=lectura.tension_neutro_estimada,
            thd_v_promedio_porcentaje=Decimal(str(lectura.thd_v_promedio_porcentaje))
            if lectura.thd_v_promedio_porcentaje is not None
            else None,
            thd_i_total_porcentaje=Decimal(str(lectura.thd_i_total_porcentaje))
            if lectura.thd_i_total_porcentaje is not None
            else None,
        )
        self.db.add(model)
        self.db.commit()

    def guardar_energia(self, acumulado: AcumuladoEnergia, prioritario: bool = True) -> None:
        """Upsert por (device_id, recorded_at) (WP2, D1).

        ``prioritario=True`` (energyio): ON DUPLICATE KEY UPDATE — sobreescribe
        cualquier fila existente para ese instante, sea de energyio (reintento) o
        de acc (llegó antes). ``prioritario=False`` (acc): INSERT IGNORE — solo
        entra si no hay fila todavía; nunca pisa un valor ya guardado.
        """
        valores = {
            "device_id": acumulado.dispositivo_id,
            "recorded_at": acumulado.registrado_en,
            "net_active_energy_kwh": acumulado.energia_activa_neta.kwh if acumulado.energia_activa_neta else None,
            "net_reactive_energy_kvarh": acumulado.energia_reactiva_neta.kvarh
            if acumulado.energia_reactiva_neta
            else None,
            "imported_active_energy_kwh": acumulado.energia_activa_importada.kwh
            if acumulado.energia_activa_importada
            else None,
            "exported_active_energy_kwh": acumulado.energia_activa_exportada.kwh
            if acumulado.energia_activa_exportada
            else None,
            "imported_reactive_energy_kvarh": acumulado.energia_reactiva_importada.kvarh
            if acumulado.energia_reactiva_importada
            else None,
            "exported_reactive_energy_kvarh": acumulado.energia_reactiva_exportada.kvarh
            if acumulado.energia_reactiva_exportada
            else None,
            "source": acumulado.fuente,
        }

        if self.db.get_bind().dialect.name == "mysql":
            stmt = mysql_insert(TelemetryEnergyModel).values(**valores)
            if prioritario:
                columnas_actualizables = {k: stmt.inserted[k] for k in valores if k not in ("device_id", "recorded_at")}
                stmt = stmt.on_duplicate_key_update(**columnas_actualizables)
            else:
                stmt = stmt.prefix_with("IGNORE")
            self.db.execute(stmt)
        else:
            # Fallback portable (usado por los tests unitarios sobre SQLite en
            # memoria: MySQL no está disponible ahí). Mismo contrato que arriba
            # — lee-decide-escribe en vez de una sentencia atómica — aceptable
            # porque en producción SIEMPRE corre la rama MySQL de más arriba.
            existente = (
                self.db.query(TelemetryEnergyModel)
                .filter(
                    TelemetryEnergyModel.device_id == acumulado.dispositivo_id,
                    TelemetryEnergyModel.recorded_at == acumulado.registrado_en,
                )
                .one_or_none()
            )
            if existente is None:
                self.db.add(TelemetryEnergyModel(**valores))
            elif prioritario:
                for campo, valor in valores.items():
                    if campo not in ("device_id", "recorded_at"):
                        setattr(existente, campo, valor)
        self.db.commit()

    def guardar_log_estado(self, log: LogEstadoDispositivo) -> None:
        model = DeviceStatusLogModel(
            device_id=log.dispositivo_id,
            recorded_at=log.registrado_en,
            wifi_rssi_dbm=log.wifi_rssi_dbm,
            wifi_calidad=log.wifi_calidad,
            ip_address=log.direccion_ip,
            uptime_seconds=log.tiempo_activo_segundos,
            raw_payload=log.payload_bruto,
        )
        self.db.add(model)
        self.db.commit()

    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        existente = (
            self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id == alerta.id).first()
            if alerta.id is not None
            else None
        )
        model = alerta_a_modelo(alerta, existente or DeviceAlertModel())
        if existente is None:
            self.db.add(model)
        self.db.commit()
        if alerta.id is None:
            alerta.id = model.id

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        severidad: str | None = None,
        limite: int = 100,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        organizacion_id: str | None = None,
    ) -> list[AlertaDispositivo]:
        q = self.db.query(DeviceAlertModel)
        if organizacion_id:
            q = (
                q.join(DeviceModel, DeviceAlertModel.device_id == DeviceModel.id)
                .join(FacilityModel, DeviceModel.facility_id == FacilityModel.id)
                .filter(FacilityModel.organization_id == organizacion_id)
            )
        if dispositivo_id:
            q = q.filter(DeviceAlertModel.device_id == dispositivo_id)
        if solo_abiertas:
            q = q.filter(DeviceAlertModel.is_resolved.is_(False))
        if severidad:
            q = q.filter(DeviceAlertModel.severity == severidad.upper())
        if desde:
            q = q.filter(DeviceAlertModel.triggered_at >= desde)
        if hasta:
            q = q.filter(DeviceAlertModel.triggered_at <= hasta)
        items = q.order_by(desc(DeviceAlertModel.triggered_at)).limit(limite).all()
        return [self._alerta_to_entity(m) for m in items]

    def obtener_alerta_por_id(self, alerta_id: int) -> AlertaDispositivo | None:
        m = self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id == alerta_id).first()
        return self._alerta_to_entity(m) if m else None

    def actualizar_thd_instantanea(
        self, dispositivo_id: str, momento: datetime, ventana_s: int, thd: dict[str, ThdFase]
    ) -> bool:
        return actualizar_thd_en_ultima_instantanea(self.db, dispositivo_id, momento, ventana_s, thd)

    def obtener_ultima_instantanea(self, dispositivo_id: str) -> LecturaInstantanea | None:
        m = (
            self.db.query(TelemetryInstantaneousModel)
            .filter(
                TelemetryInstantaneousModel.device_id == dispositivo_id,
                TelemetryInstantaneousModel.es_dato_confiable.is_(True),
            )
            .order_by(desc(TelemetryInstantaneousModel.recorded_at))
            .first()
        )
        return self._instantanea_to_entity(m) if m else None

    def obtener_ultimo_acumulado(self, dispositivo_id: str) -> AcumuladoEnergia | None:
        m = (
            self.db.query(TelemetryEnergyModel)
            .filter(TelemetryEnergyModel.device_id == dispositivo_id)
            .order_by(desc(TelemetryEnergyModel.recorded_at))
            .first()
        )
        return self._energia_to_entity(m) if m else None

    def listar_instantaneas(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None, hasta: datetime | None = None
    ) -> list[LecturaInstantanea]:
        q = self.db.query(TelemetryInstantaneousModel).filter(
            TelemetryInstantaneousModel.device_id == dispositivo_id,
            TelemetryInstantaneousModel.es_dato_confiable.is_(True),
        )
        if desde:
            q = q.filter(TelemetryInstantaneousModel.recorded_at >= desde)
        if hasta:
            q = q.filter(TelemetryInstantaneousModel.recorded_at <= hasta)
        items = q.order_by(desc(TelemetryInstantaneousModel.recorded_at)).limit(limite).all()
        return [self._instantanea_to_entity(m) for m in items]

    def iterar_instantaneas(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 10000,
        chunk_size: int = 500,
    ) -> Iterator[LecturaInstantanea]:
        offset, emitidos = 0, 0
        while emitidos < limite:
            lote = min(chunk_size, limite - emitidos)
            q = self.db.query(TelemetryInstantaneousModel).filter(
                TelemetryInstantaneousModel.device_id == dispositivo_id,
                TelemetryInstantaneousModel.es_dato_confiable.is_(True),
            )
            if desde:
                q = q.filter(TelemetryInstantaneousModel.recorded_at >= desde)
            if hasta:
                q = q.filter(TelemetryInstantaneousModel.recorded_at <= hasta)
            items = q.order_by(asc(TelemetryInstantaneousModel.recorded_at)).offset(offset).limit(lote).all()
            if not items:
                break
            for m in items:
                yield self._instantanea_to_entity(m)
                emitidos += 1
            offset += len(items)
            if len(items) < lote:
                break

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        q = self.db.query(TelemetryEnergyModel).filter(TelemetryEnergyModel.device_id == dispositivo_id)
        if desde:
            q = q.filter(TelemetryEnergyModel.recorded_at >= desde)
        items = q.order_by(desc(TelemetryEnergyModel.recorded_at)).limit(limite).all()
        return [self._energia_to_entity(m) for m in items]

    def listar_ultimos_acumulados_por_periodo(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        granularidad: str = "day",
        zona: str = "UTC",
    ) -> list[AcumuladoEnergia]:
        """Un acumulado por periodo local, resuelto en SQL con ROW_NUMBER().

        Antes: cargaba la serie cruda entera (hasta ~87 000 filas para un
        dispositivo con meses de datos) y el dominio se quedaba con el último
        valor por periodo en Python. Ahora esa reducción la hace MySQL: el
        WHERE usa el índice (device_id, recorded_at) para filtrar, y solo se
        hidrata en Python una fila por día/mes.

        Requiere las tablas de zona horaria de MySQL cargadas
        (``mysql_tzinfo_to_sql``); sin ellas, CONVERT_TZ devuelve NULL para
        cualquier zona IANA y se pierde la partición por periodo local, así
        que se falla explícito en vez de agregar en silencio por UTC.
        """
        if zona not in self._zonas_tz_verificadas:
            if self.db.execute(select(func.convert_tz(func.now(), "UTC", zona))).scalar() is None:
                raise RuntimeError(
                    f"CONVERT_TZ devolvió NULL para la zona {zona!r}: las tablas de zona horaria de "
                    "MySQL no están cargadas. Ejecutar `mysql_tzinfo_to_sql /usr/share/zoneinfo | "
                    "mysql mysql` en el servidor antes de agregar energía por periodo."
                )
            self._zonas_tz_verificadas.add(zona)

        recorded_at_local = func.convert_tz(TelemetryEnergyModel.recorded_at, "UTC", zona)
        periodo_expr = (
            func.date_format(recorded_at_local, "%Y-%m-01") if granularidad == "month" else func.date(recorded_at_local)
        )
        rn = (
            func.row_number()
            .over(partition_by=periodo_expr, order_by=desc(TelemetryEnergyModel.recorded_at))
            .label("rn")
        )

        base = self.db.query(TelemetryEnergyModel, rn.label("rn")).filter(
            TelemetryEnergyModel.device_id == dispositivo_id
        )
        if desde:
            base = base.filter(TelemetryEnergyModel.recorded_at >= desde)
        subq = base.subquery()
        modelo = aliased(TelemetryEnergyModel, subq)

        items = self.db.query(modelo).filter(subq.c.rn == 1).all()
        entidades = [self._energia_to_entity(m) for m in items]
        # El resultado está acotado al número de periodos (días/meses), nunca a la
        # cadencia de ingesta: ordenar en Python es gratis y evita depender de las
        # columnas de la subquery para el ORDER BY.
        entidades.sort(key=lambda e: e.registrado_en)
        return entidades

    def listar_potencias_para_histograma(
        self, dispositivo_id: str, desde: datetime, limite: int | None = None
    ) -> list[LecturaPotenciaTemporal]:
        q = (
            self.db.query(
                TelemetryInstantaneousModel.recorded_at,
                TelemetryInstantaneousModel.total_active_power,
            )
            .filter(
                TelemetryInstantaneousModel.device_id == dispositivo_id,
                TelemetryInstantaneousModel.recorded_at >= desde,
                TelemetryInstantaneousModel.total_active_power.isnot(None),
            )
            .order_by(asc(TelemetryInstantaneousModel.recorded_at))
        )
        if limite is not None:
            q = q.limit(limite)
        filas = q.all()
        return [LecturaPotenciaTemporal(momento=fila[0], potencia_w=float(fila[1])) for fila in filas]

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(TelemetryInstantaneousModel.id)
            .filter(TelemetryInstantaneousModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(TelemetryInstantaneousModel)
            .filter(TelemetryInstantaneousModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(TelemetryEnergyModel.id)
            .filter(TelemetryEnergyModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(TelemetryEnergyModel)
            .filter(TelemetryEnergyModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(DeviceStatusLogModel.id)
            .filter(DeviceStatusLogModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(DeviceStatusLogModel)
            .filter(DeviceStatusLogModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(DeviceAlertModel.id)
            .filter(DeviceAlertModel.is_resolved.is_(True), DeviceAlertModel.resolved_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id.in_(ids)).delete(synchronize_session=False)
        self.db.commit()
        return deleted

    def guardar_anomalia(self, device_id: str, error_s: float, recorded_at: datetime) -> None:
        """Guarda flag de coherencia baja (Capa 1: detección en ingesta)."""
        from src.infrastructure.sqlalchemy.models import TelemetriaAnomaliaModel

        anomalia = TelemetriaAnomaliaModel(
            device_id=device_id,
            recorded_at=recorded_at,
            error_s=error_s,
            flag_tipo="coherencia_baja",
            contador_consecutivos=1,
            estado="active",
        )
        self.db.add(anomalia)
        self.db.commit()

    def obtener_error_promedio(self, device_id: str, desde: datetime, hasta: datetime) -> float | None:
        """Calcula promedio de error_s en rango (Capa 2: Gauntlet)."""
        from sqlalchemy import func

        from src.infrastructure.sqlalchemy.models import TelemetriaAnomaliaModel

        result = (
            self.db.query(func.avg(TelemetriaAnomaliaModel.error_s))
            .filter(
                TelemetriaAnomaliaModel.device_id == device_id,
                TelemetriaAnomaliaModel.recorded_at >= desde,
                TelemetriaAnomaliaModel.recorded_at <= hasta,
            )
            .scalar()
        )

        return float(result) if result is not None else None

    def obtener_potencia_bucketizada_sql(
        self, device_ids: list[str], desde: datetime, hasta: datetime, bucket_segundos: int = 300
    ) -> list[float]:
        """Bucketiza y suma potencia activa en SQL, retorna lista de valores para percentil.

        Optimización para P99 con retención ilimitada: evita leer todas las lecturas crudas.
        Cada bucket promedia los registros del intervalo; múltiples dispositivos se suman por bucket.

        Args:
            device_ids: IDs de dispositivos a agregar (para nodo, múltiples).
            desde: Inicio de ventana.
            hasta: Fin de ventana.
            bucket_segundos: Tamaño del bucket (default 300 = 5 min).

        Returns:
            Lista de potencias [W] por bucket, lista vacía si sin datos.
        """
        from sqlalchemy.sql import literal_column

        if not device_ids:
            return []

        dialect = self.db.bind.dialect.name if self.db.bind else "sqlite"
        if dialect == "mysql":
            bucket_expr = literal_column(f"FLOOR(UNIX_TIMESTAMP(recorded_at) / {bucket_segundos})")
        else:
            bucket_expr = literal_column(f"CAST(STRFTIME('%s', recorded_at) AS INTEGER) / {bucket_segundos}")

        potencia_avg = func.avg(TelemetryInstantaneousModel.total_active_power).label("potencia_w")

        query = self.db.query(bucket_expr, potencia_avg)
        query = query.filter(
            TelemetryInstantaneousModel.device_id.in_(device_ids),
            TelemetryInstantaneousModel.recorded_at >= desde,
            TelemetryInstantaneousModel.recorded_at <= hasta,
            TelemetryInstantaneousModel.total_active_power.isnot(None),
            TelemetryInstantaneousModel.es_dato_confiable.is_(True),
        )
        query = query.group_by(bucket_expr).order_by(bucket_expr)

        buckets = query.all()
        return [float(potencia) for _, potencia in buckets if potencia is not None]
