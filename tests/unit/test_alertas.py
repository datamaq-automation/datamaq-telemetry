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
    )
    repo_telem.guardar_alerta(alerta)

    # Resolver la alerta
    resuelta_dto = use_case.resolver_alerta(10)

    assert resuelta_dto.id == 10
    assert resuelta_dto.esta_resuelta is True
    assert resuelta_dto.resuelta_en is not None


def test_resolver_alerta_inexistente_lanza_error():
    repo_telem = MockTelemetriaRepo()
    use_case = GestionarAlertasUseCase(repo_telem)

    with pytest.raises(AlertaNoEncontradaError):
        use_case.resolver_alerta(999)
