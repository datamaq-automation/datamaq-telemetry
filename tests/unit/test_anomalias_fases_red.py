from datetime import datetime, timezone

import pytest

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)


def test_evaluar_alerta_cruce_ti_mismatch():
    ahora = datetime.now(timezone.utc)

    # 1. Caso normal: todas las fases con FP saludable (~0.95), I=20A -> Sin alertas
    lectura_normal = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            factor_potencia=FactorPotencia(0.95),
        ),
    )
    alertas_ok = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti("dev-1", lectura_normal)
    assert len(alertas_ok) == 0

    # 2. Caso Cruce de TI en Fase S:
    # Sensor en conductor S conectado a bornera R o desfasado 120 grados:
    # I_S = 25A, FP_S = 0.20, mientras R y T tienen FP = 0.96 y 0.94 (promedio = 0.95 > 0.85)
    lectura_cruce = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(25.0),
            potencia_activa=PotenciaActiva(1100.0),
            factor_potencia=FactorPotencia(0.20),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(22.0),
            potencia_activa=PotenciaActiva(4549.6),
            factor_potencia=FactorPotencia(0.94),
        ),
    )
    alertas_cruce = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti(
        "dev-1", lectura_cruce, tipo_instalacion="CONSUMO", fases_con_ti=["R", "S", "T"]
    )
    assert len(alertas_cruce) == 1
    assert alertas_cruce[0].tipo_alerta == "CRUCE_TI_FASE"
    assert alertas_cruce[0].severidad == SeveridadAlerta.WARNING
    assert "Fase S" in alertas_cruce[0].mensaje
    assert alertas_cruce[0].categoria == "INSTALACION"

    # 3. Caso baja corriente (I=5A < 10A): Ruido residual en vacio -> No disparar
    lectura_baja_corriente = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(5.0),
            potencia_activa=PotenciaActiva(220.0),
            factor_potencia=FactorPotencia(0.20),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(22.0),
            potencia_activa=PotenciaActiva(4549.6),
            factor_potencia=FactorPotencia(0.94),
        ),
    )
    alertas_baja = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti("dev-1", lectura_baja_corriente)
    assert len(alertas_baja) == 0

    # 4. Caso instalacion solar (GENERACION_FV) -> Ignorado
    alertas_fv = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti(
        "dev-1", lectura_cruce, tipo_instalacion="GENERACION_FV"
    )
    assert len(alertas_fv) == 0


def test_evaluar_alerta_desbalance_corriente():
    ahora = datetime.now(timezone.utc)

    # 1. Caso balanceado: I_R=30A, I_S=30A, I_T=30A -> 0% desbalance -> Sin alerta
    lectura_bal = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(30.0)),
        fase_s=MedicionFase(corriente=Corriente(30.0)),
        fase_t=MedicionFase(corriente=Corriente(30.0)),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance_corriente("dev-1", lectura_bal) is None

    # 2. Caso desbalance moderado (>15%, ej ~20%): I_R=40A, I_S=30A, I_T=30A -> Warning
    lectura_warn = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(40.0)),
        fase_s=MedicionFase(corriente=Corriente(30.0)),
        fase_t=MedicionFase(corriente=Corriente(30.0)),
    )
    alerta_warn = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance_corriente("dev-1", lectura_warn)
    assert alerta_warn is not None
    assert alerta_warn.tipo_alerta == "DESBALANCE_CORRIENTE"
    assert alerta_warn.severidad == SeveridadAlerta.WARNING
    assert alerta_warn.categoria == "DESBALANCE_CORRIENTE"
    assert alerta_warn.valor_medido == pytest.approx(20.0, rel=0.05)

    # 3. Caso desbalance severo (>25%, ej ~66%): I_R=50A, I_S=20A, I_T=20A -> Critical
    lectura_crit = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(50.0)),
        fase_s=MedicionFase(corriente=Corriente(20.0)),
        fase_t=MedicionFase(corriente=Corriente(20.0)),
    )
    alerta_crit = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance_corriente("dev-1", lectura_crit)
    assert alerta_crit is not None
    assert alerta_crit.tipo_alerta == "DESBALANCE_CORRIENTE_CRITICAL"
    assert alerta_crit.severidad == SeveridadAlerta.CRITICAL

    # 4. Caso monofasico -> Ignorado
    assert (
        AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance_corriente("dev-1", lectura_crit, es_monofasico=True)
        is None
    )


def test_evaluar_alerta_secuencia_fases():
    ahora = datetime.now(timezone.utc)
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(220.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )

    # 1. Secuencia directa (RST) -> Sin alerta
    assert (
        AnalizadorCalidadEnergiaService.evaluar_alerta_secuencia_fases("dev-1", lectura, secuencia_reportada="RST")
        is None
    )

    # 2. Secuencia inversa (RTS) -> Alerta CRITICAL
    alerta_inv = AnalizadorCalidadEnergiaService.evaluar_alerta_secuencia_fases(
        "dev-1", lectura, secuencia_reportada="RTS"
    )
    assert alerta_inv is not None
    assert alerta_inv.tipo_alerta == "SECUENCIA_FASES_INVERSA"
    assert alerta_inv.severidad == SeveridadAlerta.CRITICAL
    assert alerta_inv.categoria == "SUMINISTRO"
    assert "inversa" in alerta_inv.mensaje.lower()

    # 3. Caso monofasico -> Sin alerta aunque reporte algo extrano
    assert (
        AnalizadorCalidadEnergiaService.evaluar_alerta_secuencia_fases(
            "dev-1", lectura, es_monofasico=True, secuencia_reportada="RTS"
        )
        is None
    )


def test_evaluar_alerta_sobrecompensacion_reactiva():
    ahora = datetime.now(timezone.utc)

    # 1. Caso normal inductivo (Q > 0) -> Sin alerta
    lectura_ind = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(5000.0),
        potencia_reactiva_total=PotenciaReactiva(1200.0),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alerta_sobrecompensacion_reactiva("dev-1", lectura_ind) is None

    # 2. Caso sobrecompensacion reactiva capacitiva severa (Q <= -500 var con P >= 500W)
    lectura_cap = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(4000.0),
        potencia_reactiva_total=PotenciaReactiva(-1800.0),
    )
    alerta_cap = AnalizadorCalidadEnergiaService.evaluar_alerta_sobrecompensacion_reactiva("dev-1", lectura_cap)
    assert alerta_cap is not None
    assert alerta_cap.tipo_alerta == "SOBRECOMPENSACION_REACTIVA"
    assert alerta_cap.severidad == SeveridadAlerta.WARNING
    assert alerta_cap.categoria == "FACTOR_POTENCIA"
    assert alerta_cap.valor_medido == -1800.0


def test_procesador_alertas_ingesta_anomalias_fases():
    from unittest.mock import MagicMock

    from src.application.use_cases.ingesta.procesador_alertas_ingesta import ProcesadorAlertasIngesta
    from src.domain.telemetria.entities import Dispositivo
    from src.domain.telemetria.value_objects import MacAddress

    ahora = datetime.now(timezone.utc)
    dispositivo = Dispositivo(
        id="dev-123",
        device_uid=MacAddress("AA:BB:CC:DD:EE:FF"),
        nombre="Medidor Taller",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
    )

    repo_mock = MagicMock()
    pub_mock = MagicMock()
    logger_mock = MagicMock()

    # 1. Lectura con Cruce de TI en Fase S
    lectura_cruce = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-123",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(25.0),
            potencia_activa=PotenciaActiva(1100.0),
            factor_potencia=FactorPotencia(0.20),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(22.0),
            potencia_activa=PotenciaActiva(4549.6),
            factor_potencia=FactorPotencia(0.94),
        ),
        potencia_activa_total=PotenciaActiva(9873.6),
        potencia_reactiva_total=PotenciaReactiva(2100.0),
    )

    from datetime import timedelta

    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()

    # 1. Primera lectura: registra condición de anomalía en ventana
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="AA:BB:CC:DD:EE:FF",
        lectura=lectura_cruce,
        recorded_at=ahora,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    # 2. Segunda lectura (4 seg después): confirma persistencia y despacha alerta
    ahora_2 = ahora + timedelta(seconds=4)
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="AA:BB:CC:DD:EE:FF",
        lectura=lectura_cruce,
        recorded_at=ahora_2,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    # Debe guardar la alerta en repo
    assert repo_mock.guardar_alerta.called
    alerta_guardada = repo_mock.guardar_alerta.call_args[0][0]
    assert alerta_guardada.tipo_alerta == "CRUCE_TI_FASE"
    assert alerta_guardada.fase == "S"

    # 3. Ahora llega lectura completamente sana -> Debe auto-resolver CRUCE_TI_FASE
    repo_mock.reset_mock()
    repo_mock.listar_alertas.return_value = [alerta_guardada]

    lectura_sana = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-123",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4224.0),
            factor_potencia=FactorPotencia(0.96),
        ),
        potencia_activa_total=PotenciaActiva(12672.0),
        potencia_reactiva_total=PotenciaReactiva(1200.0),
        factor_potencia_total=FactorPotencia(0.96),
    )

    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="AA:BB:CC:DD:EE:FF",
        lectura=lectura_sana,
        recorded_at=ahora,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    # Verificar que la alerta fue marcada como resuelta y persistida
    assert alerta_guardada.esta_resuelta is True
    assert repo_mock.guardar_alerta.called
