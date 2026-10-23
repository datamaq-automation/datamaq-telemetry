"""tests/unit/test_procesador_alertas_ingesta.py

Pruebas unitarias para ProcesadorAlertasIngesta y la inhibición de alertas
de factor de potencia espurias ante anomalías fasoriales / TI (Issue #64).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
    ProcesadorAlertasIngesta,
)
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


def _crear_dispositivo_san_martin() -> Dispositivo:
    return Dispositivo(
        id="D48C49F035A8",
        device_uid=MacAddress("D4:8C:49:F0:35:A8"),
        nombre="meter-lc-san-martin-medicion-01",
        modelo="Powermeter Trifásico",
        planta_id="6a182b0f-6406-4bc2-adf3-a4d2754198af",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
    )


def _crear_lectura_ti_invertido(ahora: datetime) -> LecturaInstantanea:
    # Simula la anomalía de San Martín: Fase S con TI invertido (P_S negativa, alta corriente), FP artificial colapsado
    fase_r = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(100.0),
        potencia_activa=PotenciaActiva(21000.0),
        potencia_reactiva=PotenciaReactiva(5000.0),
        potencia_aparente=PotenciaAparente(21600.0),
        factor_potencia=FactorPotencia(0.97),
    )
    fase_s = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(586.2),
        potencia_activa=PotenciaActiva(-3708.0),  # TI invertido
        potencia_reactiva=PotenciaReactiva(25000.0),
        potencia_aparente=PotenciaAparente(25300.0),
        factor_potencia=FactorPotencia(0.04),
    )
    fase_t = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(120.0),
        potencia_activa=PotenciaActiva(25000.0),
        potencia_reactiva=PotenciaReactiva(6000.0),
        potencia_aparente=PotenciaAparente(25700.0),
        factor_potencia=FactorPotencia(0.97),
    )
    return LecturaInstantanea(
        id=101,
        dispositivo_id="D48C49F035A8",
        registrado_en=ahora,
        fase_r=fase_r,
        fase_s=fase_s,
        fase_t=fase_t,
        potencia_activa_total=PotenciaActiva(42292.0),
        potencia_reactiva_total=PotenciaReactiva(36000.0),
        potencia_aparente_total=PotenciaAparente(55500.0),
        factor_potencia_total=FactorPotencia(0.04),  # Colapsado espuriamente
    )


def _crear_lectura_bajo_fp_sin_anomalia_ti(ahora: datetime) -> LecturaInstantanea:
    # Carga inductiva real con bajo factor de potencia sin inversión de TI
    fase_r = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(50.0),
        potencia_activa=PotenciaActiva(7700.0),
        potencia_reactiva=PotenciaReactiva(7800.0),
        potencia_aparente=PotenciaAparente(11000.0),
        factor_potencia=FactorPotencia(0.70),
    )
    fase_s = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(50.0),
        potencia_activa=PotenciaActiva(7700.0),
        potencia_reactiva=PotenciaReactiva(7800.0),
        potencia_aparente=PotenciaAparente(11000.0),
        factor_potencia=FactorPotencia(0.70),
    )
    fase_t = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(50.0),
        potencia_activa=PotenciaActiva(7700.0),
        potencia_reactiva=PotenciaReactiva(7800.0),
        potencia_aparente=PotenciaAparente(11000.0),
        factor_potencia=FactorPotencia(0.70),
    )
    return LecturaInstantanea(
        id=102,
        dispositivo_id="D48C49F035A8",
        registrado_en=ahora,
        fase_r=fase_r,
        fase_s=fase_s,
        fase_t=fase_t,
        potencia_activa_total=PotenciaActiva(23100.0),
        potencia_reactiva_total=PotenciaReactiva(23400.0),
        potencia_aparente_total=PotenciaAparente(33000.0),
        factor_potencia_total=FactorPotencia(0.70),
    )


def test_evaluar_fp_retorna_none_cuando_hay_anomalia_ti():
    """_evaluar_fp retorna (None, None) de forma inmediata si hay_anomalia_ti es True."""
    dispositivo = _crear_dispositivo_san_martin()
    ahora = datetime.now(timezone.utc)
    lectura = _crear_lectura_ti_invertido(ahora)
    repo = MagicMock()

    alerta_fp, alerta_sc = ProcesadorAlertasIngesta._evaluar_fp(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura,
        recorded_at=ahora,
        repo=repo,
        pub=None,
        log=None,
        hay_anomalia_ti=True,
    )

    assert alerta_fp is None
    assert alerta_sc is None
    repo.guardar_alerta.assert_not_called()


def test_evaluar_fp_funciona_normalmente_cuando_no_hay_anomalia_ti():
    """_evaluar_fp evalúa el factor de potencia si hay_anomalia_ti es False."""
    dispositivo = _crear_dispositivo_san_martin()
    ahora = datetime.now(timezone.utc)
    lectura = _crear_lectura_bajo_fp_sin_anomalia_ti(ahora)
    repo = MagicMock()

    alerta_fp, alerta_sc = ProcesadorAlertasIngesta._evaluar_fp(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura,
        recorded_at=ahora,
        repo=repo,
        pub=None,
        log=None,
        hay_anomalia_ti=False,
    )

    assert alerta_fp is not None
    assert alerta_fp.tipo_alerta == "BAJO_FACTOR_POTENCIA"
    assert alerta_sc is None


def test_procesar_alertas_inhibe_fp_ante_ti_invertido():
    """Si evaluar_alerta_ti_invertido genera alerta, no se despacha BAJO_FACTOR_POTENCIA."""
    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()
    dispositivo = _crear_dispositivo_san_martin()
    ahora = datetime.now(timezone.utc)
    lectura_1 = _crear_lectura_ti_invertido(ahora)
    lectura_2 = _crear_lectura_ti_invertido(ahora + timedelta(seconds=4))

    repo = MagicMock()

    # Lectura 1: entra en ventana de persistencia
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_1,
        recorded_at=ahora,
        repo_telemetria=repo,
    )

    # Lectura 2: persistencia confirmada
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_2,
        recorded_at=ahora + timedelta(seconds=4),
        repo_telemetria=repo,
    )

    alertas_guardadas = [args[0][0].tipo_alerta for args in repo.guardar_alerta.call_args_list]

    # Debe haberse generado alerta de TI_INVERTIDO
    assert any("TI_INVERTIDO" in a for a in alertas_guardadas)

    # NO deben generarse alertas de bajo factor de potencia ni sobrecompensación
    assert "BAJO_FACTOR_POTENCIA" not in alertas_guardadas
    assert "SOBRECOMPENSACION_REACTIVA" not in alertas_guardadas


def test_procesar_alertas_despacha_fp_cuando_ti_raw_esta_vacio():
    """Cuando no hay ninguna anomalía de TI, se despachan alertas legítimas de bajo factor de potencia."""
    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()
    dispositivo = _crear_dispositivo_san_martin()
    ahora = datetime.now(timezone.utc)
    lectura_1 = _crear_lectura_bajo_fp_sin_anomalia_ti(ahora)
    lectura_2 = _crear_lectura_bajo_fp_sin_anomalia_ti(ahora + timedelta(seconds=4))

    repo = MagicMock()

    # Lectura 1
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_1,
        recorded_at=ahora,
        repo_telemetria=repo,
    )

    # Lectura 2: confirmación de persistencia temporal
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_2,
        recorded_at=ahora + timedelta(seconds=4),
        repo_telemetria=repo,
    )

    alertas_guardadas = [args[0][0].tipo_alerta for args in repo.guardar_alerta.call_args_list]

    # Debe contener BAJO_FACTOR_POTENCIA
    assert "BAJO_FACTOR_POTENCIA" in alertas_guardadas
    # No debe contener alertas de TI
    assert not any("TI" in a for a in alertas_guardadas)
