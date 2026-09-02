"""Fase RED — Agregación de energía por periodo (day/month) y su caso de uso."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import AcumuladoEnergia, Dispositivo, EnergiaAgregada
from src.domain.telemetria.exceptions import (
    GranularidadEnergiaInvalidaError,
    ZonaHorariaInvalidaError,
)
from src.domain.telemetria.services import AgregacionEnergiaService
from src.domain.telemetria.value_objects import EnergiaActiva, GranularidadEnergia, MacAddress
from tests.unit.test_use_cases import MockDispositivosRepo, MockTelemetriaRepo

ARG = ZoneInfo("America/Argentina/Buenos_Aires")


def _acc(dispositivo_id: str, registrado_en: datetime, kwh: float) -> AcumuladoEnergia:
    return AcumuladoEnergia(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=registrado_en,
        energia_activa_neta=EnergiaActiva(kwh=kwh),
    )


# --- Tests del servicio puro ---


def test_agregacion_dia_calcula_delta_entre_dias():
    acumulados = [
        _acc("dev-1", datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), 10.0),
        _acc("dev-1", datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc), 15.0),
        _acc("dev-1", datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc), 22.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.DIA, ARG)

    assert [r.periodo for r in resultado] == [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    assert all(isinstance(r, EnergiaAgregada) for r in resultado)
    assert resultado[0].energia_activa_neta_kwh is None
    assert resultado[1].energia_activa_neta_kwh == 5.0
    assert resultado[2].energia_activa_neta_kwh == 7.0


def test_agregacion_mes_calcula_delta_entre_meses():
    acumulados = [
        _acc("dev-1", datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc), 10.0),
        _acc("dev-1", datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc), 18.0),
        _acc("dev-1", datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc), 25.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.MES, ARG)

    assert [r.periodo for r in resultado] == [date(2026, 8, 1), date(2026, 9, 1)]
    assert resultado[0].energia_activa_neta_kwh is None
    assert resultado[1].energia_activa_neta_kwh == 15.0


def test_corte_dia_en_zona_argentina():
    # Argentina en septiembre: UTC-3. 02:30 UTC = 23:30 local del día anterior.
    acumulados = [
        _acc("dev-1", datetime(2026, 9, 2, 2, 30, tzinfo=timezone.utc), 10.0),
        _acc("dev-1", datetime(2026, 9, 2, 3, 30, tzinfo=timezone.utc), 11.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.DIA, ARG)

    assert [r.periodo for r in resultado] == [date(2026, 9, 1), date(2026, 9, 2)]
    assert resultado[1].energia_activa_neta_kwh == 1.0


def test_primer_periodo_sin_referencia_es_none():
    acumulados = [
        _acc("dev-1", datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), 10.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.DIA, ARG)

    assert len(resultado) == 1
    assert resultado[0].periodo == date(2026, 9, 1)
    assert resultado[0].energia_activa_neta_kwh is None


def test_registros_sin_acumulado_se_omiten():
    acumulados = [
        AcumuladoEnergia(
            id=None,
            dispositivo_id="dev-1",
            registrado_en=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            energia_activa_neta=None,
        ),
        _acc("dev-1", datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc), 15.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.DIA, ARG)

    assert [r.periodo for r in resultado] == [date(2026, 9, 2)]
    assert resultado[0].energia_activa_neta_kwh is None


def test_orden_independiente_del_repo():
    acumulados = [
        _acc("dev-1", datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc), 22.0),
        _acc("dev-1", datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc), 10.0),
        _acc("dev-1", datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc), 15.0),
    ]

    resultado = AgregacionEnergiaService.agregar_por_periodo(acumulados, GranularidadEnergia.DIA, ARG)

    assert [r.periodo for r in resultado] == [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    assert resultado[1].energia_activa_neta_kwh == 5.0


# --- Tests del caso de uso ---


class SpyTelemetriaRepo(MockTelemetriaRepo):
    def listar_acumulados_para_agregacion(
        self, dispositivo_id: str, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        return [e for e in self.energias if e.dispositivo_id == dispositivo_id]


def _usuario_repo(dev: Dispositivo) -> tuple[SpyTelemetriaRepo, MockDispositivosRepo]:
    repo_tel = SpyTelemetriaRepo()
    repo_dev = MockDispositivosRepo()
    repo_dev.guardar(dev)
    return repo_tel, repo_dev


def _dev() -> Dispositivo:
    return Dispositivo(id="dev-1", device_uid=MacAddress("AA:BB:CC:DD:EE:FF"), nombre="Medidor")


def _dia(n: int) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    return base - timedelta(days=n)


def test_listar_energia_agregada_devuelve_dtos():
    repo_tel, repo_dev = _usuario_repo(_dev())
    repo_tel.energias = [
        _acc("dev-1", _dia(2), 10.0),
        _acc("dev-1", _dia(1), 15.0),
        _acc("dev-1", _dia(0), 22.0),
    ]
    use_case = ConsultarTelemetriaUseCase(repo_telemetria=repo_tel, repo_dispositivos=repo_dev)

    dtos = use_case.listar_energia_agregada("dev-1", "day", "America/Argentina/Buenos_Aires")

    assert len(dtos) == 3
    assert dtos[0].energia_activa_neta_kwh is None
    assert dtos[1].energia_activa_neta_kwh == 5.0
    assert dtos[2].energia_activa_neta_kwh == 7.0


def test_listar_energia_agregada_granularidad_invalida():
    repo_tel, repo_dev = _usuario_repo(_dev())
    use_case = ConsultarTelemetriaUseCase(repo_telemetria=repo_tel, repo_dispositivos=repo_dev)

    with pytest.raises(GranularidadEnergiaInvalidaError):
        use_case.listar_energia_agregada("dev-1", "week", "America/Argentina/Buenos_Aires")


def test_listar_energia_agregada_zona_invalida():
    repo_tel, repo_dev = _usuario_repo(_dev())
    use_case = ConsultarTelemetriaUseCase(repo_telemetria=repo_tel, repo_dispositivos=repo_dev)

    with pytest.raises(ZonaHorariaInvalidaError):
        use_case.listar_energia_agregada("dev-1", "day", "No/Existe")
