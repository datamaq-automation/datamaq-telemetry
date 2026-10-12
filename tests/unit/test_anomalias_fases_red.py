"""tests/unit/test_anomalias_fases_red.py."""

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


def test_evaluar_alerta_tis_en_misma_fase():
    ahora = datetime.now(timezone.utc)

    # 1. Caso real Los Constituyentes: I_R=286.6A, I_S=286.5A, FP_R=0.02, FP_S=0.85
    lectura_misma_fase = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.6),
            potencia_activa=PotenciaActiva(1300.0),
            potencia_reactiva=PotenciaReactiva(-63100.0),
            factor_potencia=FactorPotencia(0.02),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.5),
            potencia_activa=PotenciaActiva(53500.0),
            potencia_reactiva=PotenciaReactiva(33200.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(0.0),
            potencia_activa=PotenciaActiva(0.0),
            factor_potencia=FactorPotencia(1.0),
        ),
    )
    alertas = AnalizadorCalidadEnergiaService.evaluar_alerta_tis_en_misma_fase(
        "dev-constituyentes", lectura_misma_fase, fases_con_ti=["R", "S"]
    )
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta.tipo_alerta == "TIS_EN_MISMA_FASE"
    assert alerta.severidad == SeveridadAlerta.CRITICAL
    assert alerta.categoria == "INSTALACION"
    assert alerta.fase == "R-S"
    assert "Canal R" in alerta.mensaje and "Canal S" in alerta.mensaje
    assert "misma fase física" in alerta.mensaje

    # 2. Caso normal balanceado: I=50A, FP=0.92 en todas las fases -> Sin alertas
    lectura_ok = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-ok",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(50.0),
            potencia_activa=PotenciaActiva(10120.0),
            factor_potencia=FactorPotencia(0.92),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(50.0),
            potencia_activa=PotenciaActiva(10120.0),
            factor_potencia=FactorPotencia(0.92),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(50.0),
            potencia_activa=PotenciaActiva(10120.0),
            factor_potencia=FactorPotencia(0.92),
        ),
    )
    assert (
        len(
            AnalizadorCalidadEnergiaService.evaluar_alerta_tis_en_misma_fase(
                "dev-ok", lectura_ok, fases_con_ti=["R", "S", "T"]
            )
        )
        == 0
    )

    # 3. Caso baja corriente (I=5A < 10A): Ruido residual en vacío -> Sin alertas
    lectura_vacio = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-vacio",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(5.0),
            potencia_activa=PotenciaActiva(20.0),
            factor_potencia=FactorPotencia(0.02),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(5.0),
            potencia_activa=PotenciaActiva(900.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
    )
    assert (
        len(
            AnalizadorCalidadEnergiaService.evaluar_alerta_tis_en_misma_fase(
                "dev-vacio", lectura_vacio, fases_con_ti=["R", "S"]
            )
        )
        == 0
    )

    # 4. Caso solar FV -> Ignorado
    assert (
        len(
            AnalizadorCalidadEnergiaService.evaluar_alerta_tis_en_misma_fase(
                "dev-constituyentes", lectura_misma_fase, tipo_instalacion="GENERACION_FV", fases_con_ti=["R", "S"]
            )
        )
        == 0
    )


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
    assert alerta_cap.observaciones == "Banco de capacitores sobredimensionado o con pasos encendidos en vacío."


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


def test_procesador_alertas_ingesta_tis_en_misma_fase():
    from datetime import timedelta
    from unittest.mock import MagicMock

    from src.application.use_cases.ingesta.procesador_alertas_ingesta import ProcesadorAlertasIngesta
    from src.domain.telemetria.entities import Dispositivo
    from src.domain.telemetria.value_objects import MacAddress

    ahora = datetime.now(timezone.utc)
    dispositivo = Dispositivo(
        id="dev-constituyentes-1",
        device_uid=MacAddress("D4:8C:49:F0:35:A8"),
        nombre="Sala Trafo 1",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S",
    )

    repo_mock = MagicMock()
    pub_mock = MagicMock()
    logger_mock = MagicMock()

    lectura_misma_fase = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes-1",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.6),
            potencia_activa=PotenciaActiva(1300.0),
            potencia_reactiva=PotenciaReactiva(-63100.0),
            factor_potencia=FactorPotencia(0.02),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.5),
            potencia_activa=PotenciaActiva(53500.0),
            potencia_reactiva=PotenciaReactiva(33200.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
        potencia_activa_total=PotenciaActiva(54800.0),
        potencia_reactiva_total=PotenciaReactiva(-29900.0),
        factor_potencia_total=FactorPotencia(0.44),
    )

    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()

    # Muestra 1: registrar en ventana de persistencia
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_misma_fase,
        recorded_at=ahora,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    # Muestra 2 (4 seg después): confirma persistencia y despacha
    ahora_2 = ahora + timedelta(seconds=4)
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_misma_fase,
        recorded_at=ahora_2,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    assert repo_mock.guardar_alerta.called
    alerta_guardada = next(
        call.args[0]
        for call in repo_mock.guardar_alerta.call_args_list
        if call.args[0].tipo_alerta == "TIS_EN_MISMA_FASE"
    )
    assert alerta_guardada.severidad == SeveridadAlerta.CRITICAL
    assert alerta_guardada.fase == "R-S"

    # Auto-resolución al normalizar conexionado
    repo_mock.reset_mock()
    repo_mock.listar_alertas.return_value = [alerta_guardada]

    lectura_corregida = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes-1",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(140.0),
            potencia_activa=PotenciaActiva(26180.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(150.0),
            potencia_activa=PotenciaActiva(28050.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
        potencia_activa_total=PotenciaActiva(54230.0),
        potencia_reactiva_total=PotenciaReactiva(33000.0),
        factor_potencia_total=FactorPotencia(0.85),
    )

    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura_corregida,
        recorded_at=ahora,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    assert alerta_guardada.esta_resuelta is True


def test_evaluar_alerta_ti_desconectado():
    ahora = datetime.now(timezone.utc)

    # Caso Constituyentes: Fase R=285A, Fase S=284A, Fase T=0A con tension normal 220V
    lectura_ti_desconectado = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.3),
            corriente=Corriente(285.2),
            potencia_activa=PotenciaActiva(1188.0),
            factor_potencia=FactorPotencia(0.02),
        ),
        fase_s=MedicionFase(
            tension=Tension(219.1),
            corriente=Corriente(283.7),
            potencia_activa=PotenciaActiva(52575.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(
            tension=Tension(217.2),
            corriente=Corriente(0.0),
            potencia_activa=PotenciaActiva(0.0),
            factor_potencia=FactorPotencia(1.0),
        ),
    )

    alertas = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_desconectado(
        "dev-constituyentes", lectura_ti_desconectado, fases_con_ti=["R", "S", "T"]
    )
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta.tipo_alerta == "TI_DESCONECTADO"
    assert alerta.severidad == SeveridadAlerta.CRITICAL
    assert alerta.fase == "T"
    assert "Fase T" in alerta.mensaje
    assert "corriente nula" in alerta.mensaje

    # Si la fase T no estaba habilitada en fases_con_ti (ej. instalacion bifasica intencional), no debe alertar
    alertas_bifasico = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_desconectado(
        "dev-constituyentes", lectura_ti_desconectado, fases_con_ti=["R", "S"]
    )
    assert len(alertas_bifasico) == 0

    # Si todas las fases estan apagadas o carga < 10A, no debe alertar desconexion de TI
    lectura_apagada = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
    )
    alertas_apagado = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_desconectado(
        "dev-constituyentes", lectura_apagada, fases_con_ti=["R", "S", "T"]
    )
    assert len(alertas_apagado) == 0
