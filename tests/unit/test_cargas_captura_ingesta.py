"""Captura de muestras de campaña desde el camino de ingesta MQTT."""

from datetime import datetime, timedelta, timezone

from src.application.use_cases.ingesta.capturador_campana import CapturadorCampanaIngesta
from src.application.use_cases.ingesta.registro_campanas import RegistroCampanasActivas
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)
from tests.unit.test_cargas_campanas import MockCampanasRepo

MEDIDOR = "dev-casa"
AHORA = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)


def _lectura(momento: datetime, potencia: float | None = 1850.0) -> LecturaInstantanea:
    fase = MedicionFase(
        tension=Tension(221.6),
        corriente=Corriente(8.4),
        potencia_activa=PotenciaActiva(potencia) if potencia is not None else None,
        potencia_reactiva=PotenciaReactiva(12.0),
        potencia_aparente=PotenciaAparente(1861.0),
        factor_potencia=FactorPotencia(0.99),
    )
    return LecturaInstantanea(
        id=None,
        dispositivo_id=MEDIDOR,
        registrado_en=momento,
        fase_r=fase,
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(potencia) if potencia is not None else None,
        potencia_reactiva_total=PotenciaReactiva(12.0),
        potencia_aparente_total=PotenciaAparente(1861.0),
        factor_potencia_total=FactorPotencia(0.99),
    )


def _capturador(registro: RegistroCampanasActivas, repo: MockCampanasRepo) -> CapturadorCampanaIngesta:
    return CapturadorCampanaIngesta(repo, registro)


def test_sin_campana_abierta_no_se_guarda_nada():
    """El caso normal: la inmensa mayoría de las lecturas no pertenecen a una campaña."""
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()

    assert _capturador(registro, repo).capturar(MEDIDOR, _lectura(AHORA)) is False
    assert repo.muestras == {}


def test_con_campana_abierta_se_guarda_la_fila_electrica_completa():
    """El objetivo de la campaña es medir la firma entera, no solo la potencia activa."""
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))

    assert _capturador(registro, repo).capturar(MEDIDOR, _lectura(AHORA)) is True
    muestra = repo.muestras["camp-1"][0]
    assert muestra.potencia_w == 1850.0
    assert muestra.potencia_reactiva_var == 12.0
    assert muestra.factor_potencia == 0.99
    assert muestra.tension_v == 221.6
    assert muestra.corriente_a == 8.4


def test_una_lectura_sin_potencia_activa_no_aporta_a_la_firma():
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))

    assert _capturador(registro, repo).capturar(MEDIDOR, _lectura(AHORA, potencia=None)) is False


def test_un_redelivery_de_qos_1_no_duplica_la_muestra():
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))
    capturador = _capturador(registro, repo)

    primera = capturador.capturar(MEDIDOR, _lectura(AHORA))
    repetida = capturador.capturar(MEDIDOR, _lectura(AHORA))

    assert (primera, repetida) == (True, False)
    assert len(repo.muestras["camp-1"]) == 1


def test_una_campana_vencida_deja_de_capturar_aunque_nadie_la_haya_cerrado():
    """El cierre ordenado lo hace el bucle del servidor; mientras tanto no debe seguir."""
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA)

    assert _capturador(registro, repo).capturar(MEDIDOR, _lectura(AHORA + timedelta(seconds=1))) is False


def test_un_fallo_capturando_no_interrumpe_la_ingesta():
    """Perder una muestra de campaña se resuelve repitiéndola; perder telemetría, no."""

    class RepoRoto(MockCampanasRepo):
        def agregar_muestra(self, campana_id, muestra):
            raise RuntimeError("base caída")

    registro = RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))

    assert _capturador(registro, RepoRoto()).capturar(MEDIDOR, _lectura(AHORA)) is False


def test_el_registro_solo_alcanza_al_dispositivo_de_la_campana():
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))

    assert _capturador(registro, repo).capturar("otro-medidor", _lectura(AHORA)) is False


def test_desactivar_corta_la_captura():
    repo, registro = MockCampanasRepo(), RegistroCampanasActivas()
    registro.activar(MEDIDOR, "camp-1", AHORA + timedelta(minutes=10))
    registro.desactivar(MEDIDOR)

    assert _capturador(registro, repo).capturar(MEDIDOR, _lectura(AHORA)) is False
    assert registro.dispositivos_activos() == []
