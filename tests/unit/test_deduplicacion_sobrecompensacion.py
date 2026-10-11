# tests/unit/test_deduplicacion_sobrecompensacion.py
"""Regresión: no abrir dos alertas SOBRECOMPENSACION_REACTIVA para el mismo dispositivo tras un reinicio."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
    ProcesadorAlertasIngesta,
)
from src.domain.telemetria.entities import AlertaDispositivo, Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.persistencia_alertas import FiltroPersistenciaTemporalService
from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva, PotenciaReactiva, SeveridadAlerta

TIPO_SC = "SOBRECOMPENSACION_REACTIVA"
MAC = "D4:8C:49:F0:35:A8"


def _dispositivo() -> Dispositivo:
    return Dispositivo(
        id="D48C49F035A8",
        device_uid=MacAddress(MAC),
        nombre="Medidor TGBT Usina 10",
        modelo="Powermeter Trifásico",
        planta_id="c64fd625-0037-4caa-b68a-800e8e0ee548",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
    )


def _lectura_capacitiva(ahora: datetime) -> LecturaInstantanea:
    # P >= 500 W y Q <= -500 var: dispara SOBRECOMPENSACION_REACTIVA sin anomalía de TI.
    return LecturaInstantanea(
        id=None,
        dispositivo_id="D48C49F035A8",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(4000.0),
        potencia_reactiva_total=PotenciaReactiva(-1800.0),
    )


def _alerta_abierta(tipo: str) -> AlertaDispositivo:
    return AlertaDispositivo(
        id=1,
        dispositivo_id="D48C49F035A8",
        tipo_alerta=tipo,
        severidad=SeveridadAlerta.WARNING,
        mensaje="alerta abierta previa al reinicio",
    )


def _procesar_dos_lecturas_con_filtro_recien_iniciado(repo: MagicMock) -> None:
    """Simula un worker recién reiniciado: el filtro de persistencia arranca con estados vacíos."""
    dispositivo = _dispositivo()
    ahora = datetime.now(timezone.utc)
    lectura = _lectura_capacitiva(ahora)
    with patch.object(ProcesadorAlertasIngesta, "_filtro_persistencia", FiltroPersistenciaTemporalService()):
        for segundos in (0, 4):
            ProcesadorAlertasIngesta.procesar_alertas(
                dispositivo=dispositivo,
                mac_raw=MAC,
                lectura=lectura,
                recorded_at=ahora + timedelta(seconds=segundos),
                repo_telemetria=repo,
                publicador=MagicMock(),
                logger=MagicMock(),
            )


def _tipos_guardados(repo: MagicMock) -> list[str]:
    return [args[0][0].tipo_alerta for args in repo.guardar_alerta.call_args_list]


def test_reinicio_con_alerta_abierta_no_crea_otra_sobrecompensacion():
    repo = MagicMock()
    repo.listar_alertas.return_value = [_alerta_abierta(TIPO_SC)]

    _procesar_dos_lecturas_con_filtro_recien_iniciado(repo)

    assert TIPO_SC not in _tipos_guardados(repo)
    llamadas = [c.kwargs for c in repo.listar_alertas.call_args_list]
    assert {"dispositivo_id": "D48C49F035A8", "solo_abiertas": True, "limite": 1000} in llamadas


def test_sin_alerta_abierta_la_sobrecompensacion_se_crea_una_vez():
    """Control: sin alerta abierta el mismo escenario sí dispara, así el test anterior prueba la deduplicación."""
    repo = MagicMock()
    repo.listar_alertas.return_value = []

    _procesar_dos_lecturas_con_filtro_recien_iniciado(repo)

    assert _tipos_guardados(repo).count(TIPO_SC) == 1


def test_alerta_abierta_de_otro_tipo_no_bloquea_sobrecompensacion():
    repo = MagicMock()
    repo.listar_alertas.return_value = [_alerta_abierta("BAJO_FACTOR_POTENCIA")]

    _procesar_dos_lecturas_con_filtro_recien_iniciado(repo)

    assert _tipos_guardados(repo).count(TIPO_SC) == 1
