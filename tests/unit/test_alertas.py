"""tests/unit/test_alertas.py."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.domain.telemetria.entities import AlertaDispositivo
from src.domain.telemetria.exceptions import AlertaNoEncontradaError
from src.domain.telemetria.value_objects import SeveridadAlerta
from tests.unit.test_optimizacion_db import MockTelemetriaRepo


def test_listar_alertas_con_filtro_abiertas_y_device():
    repo_telem = MockTelemetriaRepo()
    use_case = GestionarAlertasUseCase(repo_telem)

    ahora = datetime.now(timezone.utc)

    # Crear 3 alertas: 2 para dev-1 (1 abierta, 1 resuelta), 1 para dev-2 (abierta)
    alerta1 = AlertaDispositivo(
        id=1,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Tensión 190V",
        esta_resuelta=False,
        disparada_en=ahora - timedelta(minutes=10),
    )
    alerta2 = AlertaDispositivo(
        id=2,
        dispositivo_id="dev-1",
        tipo_alerta="SOBRETENSION",
        severidad=SeveridadAlerta.CRITICAL,
        mensaje="Tensión 250V",
        esta_resuelta=True,
        disparada_en=ahora - timedelta(hours=1),
        resuelta_en=ahora - timedelta(minutes=30),
    )
    alerta3 = AlertaDispositivo(
        id=3,
        dispositivo_id="dev-2",
        tipo_alerta="CORTE_ENERGIA",
        severidad=SeveridadAlerta.CRITICAL,
        mensaje="Medidor sin alimentación",
        esta_resuelta=False,
        disparada_en=ahora - timedelta(minutes=5),
    )

    repo_telem.guardar_alerta(alerta1)
    repo_telem.guardar_alerta(alerta2)
    repo_telem.guardar_alerta(alerta3)

    # 1. Listar todas sin filtro
    todas = use_case.listar_alertas()
    assert len(todas) == 3

    # 2. Filtrar solo abiertas
    abiertas = use_case.listar_alertas(solo_abiertas=True)
    assert len(abiertas) == 2
    assert all(a.esta_resuelta is False for a in abiertas)

    # 3. Filtrar por dispositivo dev-1 y solo abiertas
    dev1_abiertas = use_case.listar_alertas(dispositivo_id="dev-1", solo_abiertas=True)
    assert len(dev1_abiertas) == 1
    assert dev1_abiertas[0].id == 1


def test_resolver_alerta_exitosa():
    repo_telem = MockTelemetriaRepo()
    use_case = GestionarAlertasUseCase(repo_telem)

    ahora = datetime.now(timezone.utc)
    alerta = AlertaDispositivo(
        id=10,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Tensión 195V",
        esta_resuelta=False,
        disparada_en=ahora - timedelta(minutes=15),
        fase="R",
        valor_medido=195.0,
        valor_umbral=198.0,
        unidad="V",
        categoria="TENSION",
    )
    repo_telem.guardar_alerta(alerta)

    # Resolver la alerta con observaciones técnicas
    resuelta_dto = use_case.resolver_alerta(10, observaciones="Se procedió a regular el tap del transformador.")

    assert resuelta_dto.id == 10
    assert resuelta_dto.esta_resuelta is True
    assert resuelta_dto.resuelta_en is not None
    assert resuelta_dto.observaciones == "Se procedió a regular el tap del transformador."
    assert resuelta_dto.fase == "R"
    assert resuelta_dto.valor_medido == 195.0
    assert resuelta_dto.valor_umbral == 198.0
    assert resuelta_dto.unidad == "V"
    assert resuelta_dto.categoria == "TENSION"
    assert resuelta_dto.duracion_segundos is not None
    assert resuelta_dto.duracion_segundos >= 800.0


def test_listar_alertas_filtros_severidad_y_rango_fechas():
    repo_telem = MockTelemetriaRepo()
    use_case = GestionarAlertasUseCase(repo_telem)

    ahora = datetime.now(timezone.utc)
    a_critica = AlertaDispositivo(
        id=101,
        dispositivo_id="dev-1",
        tipo_alerta="FALTA_FASE",
        severidad=SeveridadAlerta.CRITICAL,
        mensaje="Falta fase S",
        disparada_en=ahora - timedelta(minutes=5),
        fase="S",
        valor_medido=12.0,
        valor_umbral=50.0,
        unidad="V",
        categoria="SUMINISTRO",
    )
    a_warning = AlertaDispositivo(
        id=102,
        dispositivo_id="dev-1",
        tipo_alerta="BAJO_FACTOR_POTENCIA",
        severidad=SeveridadAlerta.WARNING,
        mensaje="FP 0.88",
        disparada_en=ahora - timedelta(hours=2),
        fase="TOTAL",
        valor_medido=0.88,
        valor_umbral=0.95,
        unidad="",
        categoria="FACTOR_POTENCIA",
    )
    repo_telem.guardar_alerta(a_critica)
    repo_telem.guardar_alerta(a_warning)

    # 1. Filtro por severidad CRITICAL
    criticas = use_case.listar_alertas(severidad="CRITICAL")
    assert len(criticas) == 1
    assert criticas[0].id == 101
    assert criticas[0].categoria == "SUMINISTRO"

    # 2. Filtro por rango de fechas (últimos 30 minutos)
    recientes = use_case.listar_alertas(desde=ahora - timedelta(minutes=30))
    assert len(recientes) == 1
    assert recientes[0].id == 101


def test_resolver_alerta_inexistente_lanza_error():
    repo_telem = MockTelemetriaRepo()
    use_case = GestionarAlertasUseCase(repo_telem)

    with pytest.raises(AlertaNoEncontradaError):
        use_case.resolver_alerta(999)


def test_resolver_alerta_con_publicador_y_repo_dispositivos():
    """Verifica que se publique la alerta resuelta con device_uid si repo_dispositivos está disponible."""
    from unittest.mock import MagicMock

    repo_telem = MockTelemetriaRepo()
    publicador_mock = MagicMock()
    repo_dispositivos_mock = MagicMock()

    # Mock un dispositivo que devuelve un device_uid
    dispositivo_mock = MagicMock()
    dispositivo_mock.device_uid.valor = "ECC9FFB45488"
    repo_dispositivos_mock.obtener_por_id.return_value = dispositivo_mock

    use_case = GestionarAlertasUseCase(repo_telem, publicador=publicador_mock, repo_dispositivos=repo_dispositivos_mock)

    ahora = datetime.now(timezone.utc)
    alerta = AlertaDispositivo(
        id=20,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Tensión baja",
        esta_resuelta=False,
        disparada_en=ahora - timedelta(minutes=5),
    )
    repo_telem.guardar_alerta(alerta)

    # Resolver la alerta
    resuelta_dto = use_case.resolver_alerta(20, observaciones="Regulado OK")

    # Verificar que se publicó con el device_uid
    assert resuelta_dto.id == 20
    assert resuelta_dto.esta_resuelta is True
    publicador_mock.publicar_telemetria_en_vivo.assert_called_once()
    call_args = publicador_mock.publicar_telemetria_en_vivo.call_args
    assert "m/wifi/ECC9FFB45488/alertas" in str(call_args)
