"""tests/unit/test_telemetria_repository.py — Tests unitarios para MySQLTelemetriaRepository."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    FactorPotencia,
    LecturaPotenciaTemporal,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceStatusLogModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)
from src.infrastructure.sqlalchemy.repositories.telemetria_repository import (
    MySQLTelemetriaRepository,
)

AHORA = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
DEV_ID = "dev-test-1234"


@pytest.fixture()
def mock_db() -> MagicMock:
    """Fixture que provee un Mock de Session de SQLAlchemy."""
    return MagicMock(spec=Session)


@pytest.fixture()
def repo(mock_db: MagicMock) -> MySQLTelemetriaRepository:
    """Fixture que provee la instancia de MySQLTelemetriaRepository."""
    return MySQLTelemetriaRepository(mock_db)


def _crear_medicion_fase(
    v: float = 220.0,
    i: float = 10.0,
    p: float = 2200.0,
    q: float = 100.0,
    s: float = 2202.27,
    fp: float = 0.99,
    thd_v: float = 1.5,
    thd_i: float = 2.0,
) -> MedicionFase:
    return MedicionFase(
        tension=Tension(voltios=v),
        corriente=Corriente(amperios=i),
        potencia_activa=PotenciaActiva(vatios=p),
        potencia_reactiva=PotenciaReactiva(var=q),
        potencia_aparente=PotenciaAparente(va=s),
        factor_potencia=FactorPotencia(valor=fp),
        thd_v_porcentaje=thd_v,
        thd_i_porcentaje=thd_i,
    )


def _crear_modelo_instantanea(id: int = 1, dev_id: str = DEV_ID, ts: datetime = AHORA) -> TelemetryInstantaneousModel:
    return TelemetryInstantaneousModel(
        id=id,
        device_id=dev_id,
        recorded_at=ts,
        voltage_r=Decimal("220.5"),
        current_r=Decimal("10.2"),
        active_power_r=Decimal("2249.1"),
        reactive_power_r=Decimal("100.0"),
        apparent_power_r=Decimal("2251.3"),
        power_factor_r=Decimal("0.99"),
        thd_v_r=Decimal("1.5"),
        thd_i_r=Decimal("2.1"),
        voltage_s=Decimal("221.0"),
        current_s=Decimal("10.1"),
        active_power_s=Decimal("2232.1"),
        reactive_power_s=Decimal("95.0"),
        apparent_power_s=Decimal("2234.1"),
        power_factor_s=Decimal("0.99"),
        thd_v_s=Decimal("1.4"),
        thd_i_s=Decimal("2.0"),
        voltage_t=Decimal("219.8"),
        current_t=Decimal("10.3"),
        active_power_t=Decimal("2263.9"),
        reactive_power_t=Decimal("105.0"),
        apparent_power_t=Decimal("2266.3"),
        power_factor_t=Decimal("0.99"),
        thd_v_t=Decimal("1.6"),
        thd_i_t=Decimal("2.2"),
        total_active_power=Decimal("6745.1"),
        total_reactive_power=Decimal("300.0"),
        total_apparent_power=Decimal("6751.7"),
        total_power_factor=Decimal("0.99"),
        desbalance_tension_porcentaje=Decimal("0.3"),
        current_n=Decimal("0.5"),
        voltage_linea_V=Decimal("380.0"),
        tension_neutro_estimada=Decimal("1.2"),
        thd_v_promedio_porcentaje=Decimal("1.5"),
        thd_i_total_porcentaje=Decimal("2.1"),
    )


def _crear_modelo_energia(id: int = 1, dev_id: str = DEV_ID, ts: datetime = AHORA) -> TelemetryEnergyModel:
    return TelemetryEnergyModel(
        id=id,
        device_id=dev_id,
        recorded_at=ts,
        net_active_energy_kwh=Decimal("1234.567"),
        net_reactive_energy_kvarh=Decimal("234.567"),
        imported_active_energy_kwh=Decimal("1300.000"),
        exported_active_energy_kwh=Decimal("65.433"),
        imported_reactive_energy_kvarh=Decimal("250.000"),
        exported_reactive_energy_kvarh=Decimal("15.433"),
    )


def _crear_modelo_alerta(id: int = 1, dev_id: str = DEV_ID, ts: datetime = AHORA) -> DeviceAlertModel:
    return DeviceAlertModel(
        id=id,
        device_id=dev_id,
        alert_type="SOBRETENSION",
        severity="CRITICAL",
        message="Tensión R fuera de rango",
        is_resolved=False,
        triggered_at=ts,
        resolved_at=None,
        phase="R",
        measured_value=Decimal("255.50"),
        threshold_value=Decimal("245.00"),
        unit="V",
        category="CALIDAD_RED",
        notes="Revisar transformador",
    )


class TestInitRepositorio:
    """Tests de inicialización."""

    def test_init_asigna_db(self, mock_db: MagicMock):
        repo = MySQLTelemetriaRepository(mock_db)
        assert repo.db is mock_db


class TestGuardarInstantanea:
    """Tests para guardar_instantanea."""

    def test_guardar_instantanea_completa(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        lectura = LecturaInstantanea(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=AHORA,
            fase_r=_crear_medicion_fase(220.0, 10.0, 2200.0, 100.0, 2202.27, 0.99, 1.5, 2.0),
            fase_s=_crear_medicion_fase(221.0, 9.8, 2165.8, 90.0, 2167.67, 0.98, 1.6, 2.1),
            fase_t=_crear_medicion_fase(219.0, 10.2, 2233.8, 110.0, 2236.5, 0.99, 1.4, 1.9),
            potencia_activa_total=PotenciaActiva(vatios=6599.6),
            potencia_reactiva_total=PotenciaReactiva(var=300.0),
            potencia_aparente_total=PotenciaAparente(va=6606.44),
            factor_potencia_total=FactorPotencia(valor=0.99),
            desbalance_tension_porcentaje=0.5,
            corriente_neutro_estimada=Corriente(amperios=0.8),
            voltage_linea_V=380.0,
            tension_neutro_estimada=1.5,
            thd_v_promedio_porcentaje=1.5,
            thd_i_total_porcentaje=2.0,
        )

        repo.guardar_instantanea(lectura)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model_guardado = mock_db.add.call_args[0][0]
        assert isinstance(model_guardado, TelemetryInstantaneousModel)
        assert model_guardado.device_id == DEV_ID
        assert model_guardado.recorded_at == AHORA
        assert model_guardado.voltage_r == 220.0
        assert model_guardado.current_r == 10.0
        assert model_guardado.active_power_r == 2200.0
        assert model_guardado.reactive_power_r == 100.0
        assert model_guardado.apparent_power_r == 2202.27
        assert model_guardado.power_factor_r == 0.99
        assert model_guardado.thd_v_r == Decimal("1.5")
        assert model_guardado.thd_i_r == Decimal("2.0")
        assert model_guardado.voltage_s == 221.0
        assert model_guardado.voltage_t == 219.0
        assert model_guardado.total_active_power == 6599.6
        assert model_guardado.total_reactive_power == 300.0
        assert model_guardado.total_apparent_power == 6606.44
        assert model_guardado.total_power_factor == 0.99
        assert model_guardado.desbalance_tension_porcentaje == 0.5
        assert model_guardado.current_n == 0.8
        assert model_guardado.voltage_linea_V == 380.0
        assert model_guardado.tension_neutro_estimada == 1.5
        assert model_guardado.thd_v_promedio_porcentaje == Decimal("1.5")
        assert model_guardado.thd_i_total_porcentaje == Decimal("2.0")

    def test_guardar_instantanea_minima(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        fase_vacia = MedicionFase()
        lectura = LecturaInstantanea(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=AHORA,
            fase_r=fase_vacia,
            fase_s=fase_vacia,
            fase_t=fase_vacia,
        )

        repo.guardar_instantanea(lectura)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model_guardado = mock_db.add.call_args[0][0]
        assert model_guardado.voltage_r is None
        assert model_guardado.current_r is None
        assert model_guardado.active_power_r is None
        assert model_guardado.thd_v_r is None
        assert model_guardado.thd_i_r is None
        assert model_guardado.total_active_power is None
        assert model_guardado.current_n is None
        assert model_guardado.thd_v_promedio_porcentaje is None
        assert model_guardado.thd_i_total_porcentaje is None


class TestGuardarEnergia:
    """Tests para guardar_energia."""

    def test_guardar_energia_completa(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        acumulado = AcumuladoEnergia(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=AHORA,
            energia_activa_neta=EnergiaActiva(kwh=1000.5),
            energia_reactiva_neta=EnergiaReactiva(kvarh=250.2),
            energia_activa_importada=EnergiaActiva(kwh=1050.0),
            energia_activa_exportada=EnergiaActiva(kwh=49.5),
            energia_reactiva_importada=EnergiaReactiva(kvarh=260.0),
            energia_reactiva_exportada=EnergiaReactiva(kvarh=9.8),
        )

        repo.guardar_energia(acumulado)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model = mock_db.add.call_args[0][0]
        assert isinstance(model, TelemetryEnergyModel)
        assert model.device_id == DEV_ID
        assert model.recorded_at == AHORA
        assert model.net_active_energy_kwh == 1000.5
        assert model.net_reactive_energy_kvarh == 250.2
        assert model.imported_active_energy_kwh == 1050.0
        assert model.exported_active_energy_kwh == 49.5
        assert model.imported_reactive_energy_kvarh == 260.0
        assert model.exported_reactive_energy_kvarh == 9.8

    def test_guardar_energia_minima(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        acumulado = AcumuladoEnergia(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=AHORA,
        )

        repo.guardar_energia(acumulado)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model = mock_db.add.call_args[0][0]
        assert model.net_active_energy_kwh is None
        assert model.net_reactive_energy_kvarh is None
        assert model.imported_active_energy_kwh is None
        assert model.exported_active_energy_kwh is None
        assert model.imported_reactive_energy_kvarh is None
        assert model.exported_reactive_energy_kvarh is None


class TestGuardarLogEstado:
    """Tests para guardar_log_estado."""

    def test_guardar_log_estado_completo(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        log = LogEstadoDispositivo(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=AHORA,
            wifi_rssi_dbm=-65,
            wifi_calidad=80,
            direccion_ip="192.168.1.105",
            tiempo_activo_segundos=86400,
            payload_bruto={"status": "ok", "fw": "1.0.4"},
        )

        repo.guardar_log_estado(log)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model = mock_db.add.call_args[0][0]
        assert isinstance(model, DeviceStatusLogModel)
        assert model.device_id == DEV_ID
        assert model.recorded_at == AHORA
        assert model.wifi_rssi_dbm == -65
        assert model.wifi_calidad == 80
        assert model.ip_address == "192.168.1.105"
        assert model.uptime_seconds == 86400
        assert model.raw_payload == {"status": "ok", "fw": "1.0.4"}


class TestGuardarAlerta:
    """Tests para guardar_alerta."""

    def test_guardar_alerta_nueva_sin_id(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        alerta = AlertaDispositivo(
            id=None,
            dispositivo_id=DEV_ID,
            tipo_alerta="SUBTENSION",
            severidad=SeveridadAlerta.WARNING,
            mensaje="Tensión baja en Fase S",
            esta_resuelta=False,
            disparada_en=AHORA,
            fase="S",
            valor_medido=195.5,
            valor_umbral=205.0,
            unidad="V",
            categoria="TENSION",
            observaciones="Corte parcial de suministro",
        )

        def simular_autoincrement(m):
            m.id = 55

        mock_db.add.side_effect = simular_autoincrement

        repo.guardar_alerta(alerta)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        model = mock_db.add.call_args[0][0]
        assert isinstance(model, DeviceAlertModel)
        assert model.device_id == DEV_ID
        assert model.alert_type == "SUBTENSION"
        assert model.severity == "WARNING"
        assert model.measured_value == Decimal("195.5")
        assert model.threshold_value == Decimal("205.0")
        assert alerta.id == 55

    def test_guardar_alerta_existente_actualiza(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        modelo_existente = _crear_modelo_alerta(id=42, dev_id=DEV_ID)
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.first.return_value = modelo_existente
        mock_db.query.return_value = q_mock

        alerta_modificada = AlertaDispositivo(
            id=42,
            dispositivo_id=DEV_ID,
            tipo_alerta="SOBRETENSION",
            severidad=SeveridadAlerta.INFO,
            mensaje="Alerta resuelta automáticamente",
            esta_resuelta=True,
            disparada_en=AHORA,
            resuelta_en=AHORA,
            fase="R",
            valor_medido=220.0,
            valor_umbral=240.0,
            unidad="V",
            categoria="CALIDAD_RED",
            observaciones="Normalizado",
        )

        repo.guardar_alerta(alerta_modificada)

        mock_db.query.assert_called_once_with(DeviceAlertModel)
        assert modelo_existente.severity == "INFO"
        assert modelo_existente.message == "Alerta resuelta automáticamente"
        assert modelo_existente.is_resolved is True
        assert modelo_existente.resolved_at == AHORA
        assert modelo_existente.measured_value == Decimal("220.0")
        assert modelo_existente.threshold_value == Decimal("240.0")
        assert modelo_existente.notes == "Normalizado"
        mock_db.commit.assert_called_once()
        mock_db.add.assert_not_called()

    def test_guardar_alerta_con_id_no_encontrada_en_db(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.first.return_value = None
        mock_db.query.return_value = q_mock

        alerta = AlertaDispositivo(
            id=999,
            dispositivo_id=DEV_ID,
            tipo_alerta="CORTE",
            severidad=SeveridadAlerta.CRITICAL,
            mensaje="Corte total",
            esta_resuelta=False,
            disparada_en=AHORA,
            valor_medido=None,
            valor_umbral=None,
        )

        repo.guardar_alerta(alerta)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert alerta.id == 999

    def test_guardar_alerta_con_valores_medidos_nulos(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        alerta = AlertaDispositivo(
            id=None,
            dispositivo_id=DEV_ID,
            tipo_alerta="DESCONEXION",
            severidad=SeveridadAlerta.WARNING,
            mensaje="Dispositivo no responde",
            valor_medido=None,
            valor_umbral=None,
        )

        repo.guardar_alerta(alerta)

        model = mock_db.add.call_args[0][0]
        assert model.measured_value is None
        assert model.threshold_value is None


class TestListarAlertas:
    """Tests para listar_alertas."""

    def test_listar_alertas_sin_filtros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        modelo1 = _crear_modelo_alerta(id=1)
        modelo2 = _crear_modelo_alerta(id=2)
        q_mock.all.return_value = [modelo1, modelo2]
        mock_db.query.return_value = q_mock

        alertas = repo.listar_alertas()

        mock_db.query.assert_called_once_with(DeviceAlertModel)
        q_mock.order_by.assert_called_once()
        q_mock.limit.assert_called_once_with(100)
        assert len(alertas) == 2
        assert alertas[0].id == 1
        assert alertas[1].id == 2

    def test_listar_alertas_con_todos_los_filtros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_alerta(id=10)]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        hasta = datetime(2026, 9, 12, 23, 59, 59, tzinfo=timezone.utc)

        alertas = repo.listar_alertas(
            dispositivo_id=DEV_ID,
            solo_abiertas=True,
            severidad="critical",
            limite=25,
            desde=desde,
            hasta=hasta,
        )

        assert q_mock.filter.call_count == 5
        q_mock.limit.assert_called_once_with(25)
        assert len(alertas) == 1
        assert alertas[0].id == 10


class TestObtenerAlertaPorId:
    """Tests para obtener_alerta_por_id."""

    def test_obtener_alerta_encontrada(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.first.return_value = _crear_modelo_alerta(id=77)
        mock_db.query.return_value = q_mock

        alerta = repo.obtener_alerta_por_id(77)

        assert alerta is not None
        assert alerta.id == 77
        assert alerta.tipo_alerta == "SOBRETENSION"

    def test_obtener_alerta_no_encontrada(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.first.return_value = None
        mock_db.query.return_value = q_mock

        alerta = repo.obtener_alerta_por_id(9999)

        assert alerta is None


class TestObtenerUltimaInstantanea:
    """Tests para obtener_ultima_instantanea."""

    def test_obtener_ultima_instantanea_encontrada(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.first.return_value = _crear_modelo_instantanea(id=88)
        mock_db.query.return_value = q_mock

        instantanea = repo.obtener_ultima_instantanea(DEV_ID)

        assert instantanea is not None
        assert instantanea.id == 88
        assert instantanea.dispositivo_id == DEV_ID
        assert instantanea.fase_r.tension.voltios == 220.5

    def test_obtener_ultima_instantanea_no_encontrada(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.first.return_value = None
        mock_db.query.return_value = q_mock

        instantanea = repo.obtener_ultima_instantanea(DEV_ID)

        assert instantanea is None


class TestObtenerUltimoAcumulado:
    """Tests para obtener_ultimo_acumulado."""

    def test_obtener_ultimo_acumulado_encontrado(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.first.return_value = _crear_modelo_energia(id=99)
        mock_db.query.return_value = q_mock

        acumulado = repo.obtener_ultimo_acumulado(DEV_ID)

        assert acumulado is not None
        assert acumulado.id == 99
        assert acumulado.dispositivo_id == DEV_ID
        assert acumulado.energia_activa_neta.kwh == 1234.567

    def test_obtener_ultimo_acumulado_no_encontrado(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.first.return_value = None
        mock_db.query.return_value = q_mock

        acumulado = repo.obtener_ultimo_acumulado(DEV_ID)

        assert acumulado is None


class TestListarInstantaneas:
    """Tests para listar_instantaneas."""

    def test_listar_instantaneas_sin_desde(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_instantanea(id=1), _crear_modelo_instantanea(id=2)]
        mock_db.query.return_value = q_mock

        resultado = repo.listar_instantaneas(dispositivo_id=DEV_ID, limite=10)

        mock_db.query.assert_called_once_with(TelemetryInstantaneousModel)
        q_mock.filter.assert_called_once()
        q_mock.limit.assert_called_once_with(10)
        assert len(resultado) == 2

    def test_listar_instantaneas_con_desde(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_instantanea(id=1)]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
        resultado = repo.listar_instantaneas(dispositivo_id=DEV_ID, limite=5, desde=desde)

        assert q_mock.filter.call_count == 2
        assert len(resultado) == 1


class TestIterarInstantaneas:
    """Tests para iterar_instantaneas (generador paginado por chunks)."""

    def test_iterar_vacio(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.offset.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = []
        mock_db.query.return_value = q_mock

        elementos = list(repo.iterar_instantaneas(DEV_ID))

        assert elementos == []

    def test_iterar_un_solo_chunk_menor_que_lote(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.offset.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_instantanea(id=1), _crear_modelo_instantanea(id=2)]
        mock_db.query.return_value = q_mock

        elementos = list(repo.iterar_instantaneas(DEV_ID, chunk_size=5))

        assert len(elementos) == 2
        assert elementos[0].id == 1
        assert elementos[1].id == 2

    def test_iterar_multiples_chunks(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.offset.return_value = q_mock
        q_mock.limit.return_value = q_mock

        chunk1 = [_crear_modelo_instantanea(id=1), _crear_modelo_instantanea(id=2)]
        chunk2 = [_crear_modelo_instantanea(id=3)]
        q_mock.all.side_effect = [chunk1, chunk2]
        mock_db.query.return_value = q_mock

        elementos = list(repo.iterar_instantaneas(DEV_ID, chunk_size=2, limite=10))

        assert len(elementos) == 3
        assert [e.id for e in elementos] == [1, 2, 3]
        assert q_mock.offset.call_args_list[0][0][0] == 0
        assert q_mock.offset.call_args_list[1][0][0] == 2

    def test_iterar_alcanza_limite_exacto(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.offset.return_value = q_mock
        q_mock.limit.return_value = q_mock

        chunk1 = [_crear_modelo_instantanea(id=1)]
        chunk2 = [_crear_modelo_instantanea(id=2)]
        q_mock.all.side_effect = [chunk1, chunk2]
        mock_db.query.return_value = q_mock

        elementos = list(repo.iterar_instantaneas(DEV_ID, limite=2, chunk_size=1))

        assert len(elementos) == 2
        assert [e.id for e in elementos] == [1, 2]

    def test_iterar_con_filtros_desde_y_hasta(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.offset.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_instantanea(id=1)]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc)
        hasta = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)

        elementos = list(repo.iterar_instantaneas(DEV_ID, desde=desde, hasta=hasta, chunk_size=5))

        assert len(elementos) == 1
        assert q_mock.filter.call_count == 3


class TestListarEnergias:
    """Tests para listar_energias."""

    def test_listar_energias_sin_desde(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_energia(id=1), _crear_modelo_energia(id=2)]
        mock_db.query.return_value = q_mock

        resultado = repo.listar_energias(DEV_ID, limite=10)

        mock_db.query.assert_called_once_with(TelemetryEnergyModel)
        q_mock.filter.assert_called_once()
        q_mock.limit.assert_called_once_with(10)
        assert len(resultado) == 2

    def test_listar_energias_con_desde(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [_crear_modelo_energia(id=1)]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        resultado = repo.listar_energias(DEV_ID, limite=5, desde=desde)

        assert q_mock.filter.call_count == 2
        assert len(resultado) == 1


class TestListarUltimosAcumuladosPorPeriodo:
    """Tests para listar_ultimos_acumulados_por_periodo (WP1: agregación en SQL)."""

    def _mock_query_chain(self, mock_db: MagicMock, filas: list) -> MagicMock:
        """El método hace dos self.db.query(...): uno para la subquery (con rn) y
        otro sobre el alias filtrando rn == 1. Ambos pasan por el mismo mock de
        Session.query, así que se configura para devolver una cadena servible en
        cualquier orden de encadenamiento."""
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.subquery.return_value = MagicMock()
        q_mock.order_by.return_value = q_mock
        q_mock.all.return_value = filas
        mock_db.query.return_value = q_mock
        return q_mock

    def test_falla_explicito_si_convert_tz_devuelve_null(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        """Sin las tablas de zona horaria de MySQL cargadas, CONVERT_TZ devuelve NULL:
        no debe agregarse en silencio por UTC, debe fallar con un mensaje accionable."""
        mock_db.execute.return_value.scalar.return_value = None

        with pytest.raises(RuntimeError, match="tablas de zona horaria"):
            repo.listar_ultimos_acumulados_por_periodo(
                DEV_ID, granularidad="day", zona="America/Argentina/Buenos_Aires"
            )

    def test_listar_sin_desde(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        mock_db.execute.return_value.scalar.return_value = datetime(2026, 9, 12, 7, 0, 0)
        q_mock = self._mock_query_chain(mock_db, [_crear_modelo_energia(id=1), _crear_modelo_energia(id=2)])

        resultado = repo.listar_ultimos_acumulados_por_periodo(DEV_ID, granularidad="day", zona="UTC")

        assert q_mock.filter.called
        assert len(resultado) == 2

    def test_listar_con_desde_filtra_por_recorded_at(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        mock_db.execute.return_value.scalar.return_value = datetime(2026, 9, 12, 7, 0, 0)
        self._mock_query_chain(mock_db, [_crear_modelo_energia(id=1)])

        desde = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        resultado = repo.listar_ultimos_acumulados_por_periodo(DEV_ID, desde=desde, granularidad="day", zona="UTC")

        assert len(resultado) == 1

    def test_granularidad_month_no_lanza(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        """Cubre la rama DATE_FORMAT(...,'%Y-%m-01') para granularidad mensual."""
        mock_db.execute.return_value.scalar.return_value = datetime(2026, 9, 12, 7, 0, 0)
        self._mock_query_chain(mock_db, [_crear_modelo_energia(id=1)])

        resultado = repo.listar_ultimos_acumulados_por_periodo(DEV_ID, granularidad="month", zona="UTC")

        assert len(resultado) == 1


class TestListarPotenciasParaHistograma:
    """Tests para listar_potencias_para_histograma."""

    def test_listar_potencias_sin_limite(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.all.return_value = [
            (datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc), Decimal("1500.5")),
            (datetime(2026, 9, 12, 10, 1, 0, tzinfo=timezone.utc), Decimal("2100.0")),
        ]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
        resultado = repo.listar_potencias_para_histograma(DEV_ID, desde=desde)

        assert len(resultado) == 2
        assert isinstance(resultado[0], LecturaPotenciaTemporal)
        assert resultado[0].potencia_w == 1500.5
        assert resultado[1].potencia_w == 2100.0
        q_mock.limit.assert_not_called()

    def test_listar_potencias_con_limite(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_mock = MagicMock()
        q_mock.filter.return_value = q_mock
        q_mock.order_by.return_value = q_mock
        q_mock.limit.return_value = q_mock
        q_mock.all.return_value = [(datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc), Decimal("3000.0"))]
        mock_db.query.return_value = q_mock

        desde = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
        resultado = repo.listar_potencias_para_histograma(DEV_ID, desde=desde, limite=50)

        q_mock.limit.assert_called_once_with(50)
        assert len(resultado) == 1
        assert resultado[0].potencia_w == 3000.0


class TestPurgarMetodos:
    """Tests para métodos de purga en lotes."""

    def test_purgar_instantaneas_sin_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = []
        mock_db.query.return_value = q_select

        eliminados = repo.purgar_instantaneas_anteriores_a(AHORA)

        assert eliminados == 0
        mock_db.commit.assert_not_called()

    def test_purgar_instantaneas_con_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = [(101,), (102,), (103,)]

        q_delete = MagicMock()
        q_delete.filter.return_value = q_delete
        q_delete.delete.return_value = 3

        mock_db.query.side_effect = [q_select, q_delete]

        eliminados = repo.purgar_instantaneas_anteriores_a(AHORA, batch_size=500)

        assert eliminados == 3
        q_select.limit.assert_called_once_with(500)
        q_delete.delete.assert_called_once_with(synchronize_session=False)
        mock_db.commit.assert_called_once()

    def test_purgar_energias_sin_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = []
        mock_db.query.return_value = q_select

        eliminados = repo.purgar_energias_anteriores_a(AHORA)

        assert eliminados == 0
        mock_db.commit.assert_not_called()

    def test_purgar_energias_con_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = [(201,), (202,)]

        q_delete = MagicMock()
        q_delete.filter.return_value = q_delete
        q_delete.delete.return_value = 2

        mock_db.query.side_effect = [q_select, q_delete]

        eliminados = repo.purgar_energias_anteriores_a(AHORA, batch_size=200)

        assert eliminados == 2
        q_select.limit.assert_called_once_with(200)
        q_delete.delete.assert_called_once_with(synchronize_session=False)
        mock_db.commit.assert_called_once()

    def test_purgar_status_logs_sin_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = []
        mock_db.query.return_value = q_select

        eliminados = repo.purgar_status_logs_anteriores_a(AHORA)

        assert eliminados == 0
        mock_db.commit.assert_not_called()

    def test_purgar_status_logs_con_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = [(301,)]

        q_delete = MagicMock()
        q_delete.filter.return_value = q_delete
        q_delete.delete.return_value = 1

        mock_db.query.side_effect = [q_select, q_delete]

        eliminados = repo.purgar_status_logs_anteriores_a(AHORA)

        assert eliminados == 1
        q_select.limit.assert_called_once_with(1000)
        q_delete.delete.assert_called_once_with(synchronize_session=False)
        mock_db.commit.assert_called_once()

    def test_purgar_alertas_resueltas_sin_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = []
        mock_db.query.return_value = q_select

        eliminados = repo.purgar_alertas_resueltas_anteriores_a(AHORA)

        assert eliminados == 0
        mock_db.commit.assert_not_called()

    def test_purgar_alertas_resueltas_con_registros(self, repo: MySQLTelemetriaRepository, mock_db: MagicMock):
        q_select = MagicMock()
        q_select.filter.return_value = q_select
        q_select.limit.return_value = q_select
        q_select.all.return_value = [(401,), (402,)]

        q_delete = MagicMock()
        q_delete.filter.return_value = q_delete
        q_delete.delete.return_value = 2

        mock_db.query.side_effect = [q_select, q_delete]

        eliminados = repo.purgar_alertas_resueltas_anteriores_a(AHORA, batch_size=100)

        assert eliminados == 2
        q_select.limit.assert_called_once_with(100)
        q_delete.delete.assert_called_once_with(synchronize_session=False)
        mock_db.commit.assert_called_once()
