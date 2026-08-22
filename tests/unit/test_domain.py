import pytest

from src.domain.telemetria.exceptions import (
    FactorPotenciaInvalidoError,
    MacAddressInvalidaError,
    TensionInvalidaError,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    FactorPotencia,
    MacAddress,
    Tension,
)


def test_mac_address_valida():
    mac = MacAddress("d4:8c:49:f0:35:64")
    assert mac.valor == "D48C49F03564"
    assert mac.formateada() == "D4:8C:49:F0:35:64"


def test_mac_address_invalida():
    with pytest.raises(MacAddressInvalidaError):
        MacAddress("ZZ:8C:49:F0:35:64")


def test_tension_rango():
    t = Tension(220.5)
    assert t.voltios == 220.5

    with pytest.raises(TensionInvalidaError):
        Tension(-10.0)


def test_factor_potencia_rango():
    fp = FactorPotencia(0.95)
    assert fp.valor == 0.95

    with pytest.raises(FactorPotenciaInvalidoError):
        FactorPotencia(1.5)


def test_calculo_potencia_trifasica():
    total = AnalizadorCalidadEnergiaService.calcular_potencia_trifasica_activa(100.5, 200.25, 300.0)
    assert total is not None
    assert total.vatios == 600.75


def test_calculo_desbalance_tension_balanceado():
    vur = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(220.0, 220.0, 220.0)
    assert vur == 0.0


def test_calculo_desbalance_tension_desbalanceado():
    # V_prom = 220.0, max(|230-220|, |220-220|, |210-220|) = 10.0 -> (10/220)*100 = 4.55%
    vur = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(230.0, 220.0, 210.0)
    assert vur == 4.55

    # V_prom = 220.0, max(|220-220|, |215-220|, |225-220|) = 5.0 -> (5/220)*100 = 2.27%
    vur2 = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(220.0, 215.0, 225.0)
    assert vur2 == 2.27


def test_calculo_desbalance_tension_fases_incompletas_o_cero():
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_tension(220.0, None, 220.0) is None
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_tension(None, None, None) is None
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_tension(0.0, 0.0, 0.0) is None


def test_evaluar_alerta_desbalance():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import SeveridadAlerta

    ahora = datetime.now(timezone.utc)

    # Caso 1: VUR <= 2.0% (Normal)
    lectura_normal = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(221.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(219.0)),
        desbalance_tension_porcentaje=0.45,
    )
    alerta_norm = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance("dev-1", lectura_normal)
    assert alerta_norm is None

    # Caso 2: 2.0% < VUR <= 3.0% (WARNING)
    lectura_warning = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(226.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(214.0)),
        desbalance_tension_porcentaje=2.73,
    )
    alerta_w = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance("dev-1", lectura_warning)
    assert alerta_w is not None
    assert alerta_w.tipo_alerta == "DESBALANCE_TENSION"
    assert alerta_w.severidad == SeveridadAlerta.WARNING
    assert "2.73%" in alerta_w.mensaje

    # Caso 3: VUR > 3.0% (CRITICAL)
    lectura_critica = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(232.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(208.0)),
        desbalance_tension_porcentaje=5.45,
    )
    alerta_c = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance("dev-1", lectura_critica)
    assert alerta_c is not None
    assert alerta_c.tipo_alerta == "DESBALANCE_TENSION"
    assert alerta_c.severidad == SeveridadAlerta.CRITICAL
    assert "5.45%" in alerta_c.mensaje


def test_evaluar_alerta_tension_esquema_dos_niveles():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import SeveridadAlerta

    ahora = datetime.now(timezone.utc)

    # 1. Normal (198V a 242V)
    lectura_ok = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(220.0)),
        fase_s=MedicionFase(tension=Tension(225.0)),
        fase_t=MedicionFase(tension=Tension(218.0)),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_ok) is None

    # 2. Subtensión Warning ENRE (190V <= V < 198V)
    lectura_sub_warn = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(195.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_sub_w = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_sub_warn)
    assert alerta_sub_w is not None
    assert alerta_sub_w.tipo_alerta == "BAJA_TENSION"
    assert alerta_sub_w.severidad == SeveridadAlerta.WARNING
    assert "195.0V" in alerta_sub_w.mensaje

    # 3. Subtensión Crítica (V < 190V)
    lectura_sub_crit = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(185.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_sub_c = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_sub_crit)
    assert alerta_sub_c is not None
    assert alerta_sub_c.tipo_alerta == "BAJA_TENSION"
    assert alerta_sub_c.severidad == SeveridadAlerta.CRITICAL

    # 4. Sobretensión Warning ENRE (242V < V <= 248V)
    lectura_sobre_warn = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(245.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_sobre_w = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_sobre_warn)
    assert alerta_sobre_w is not None
    assert alerta_sobre_w.tipo_alerta == "SOBRETENSION"
    assert alerta_sobre_w.severidad == SeveridadAlerta.WARNING
    assert "245.0V" in alerta_sobre_w.mensaje

    # 5. Sobretensión Crítica (V > 248V)
    lectura_sobre_crit = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(252.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_sobre_c = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_sobre_crit)
    assert alerta_sobre_c is not None
    assert alerta_sobre_c.tipo_alerta == "SOBRETENSION"
    assert alerta_sobre_c.severidad == SeveridadAlerta.CRITICAL

    # 6. Prioridad: Fase R en WARNING y Fase S en CRITICAL -> CRITICAL
    lectura_mixta = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(195.0)),  # WARNING
        fase_s=MedicionFase(tension=Tension(255.0)),  # CRITICAL
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_mix = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_mixta)
    assert alerta_mix is not None
    assert alerta_mix.severidad == SeveridadAlerta.CRITICAL
    assert alerta_mix.tipo_alerta == "SOBRETENSION"


def test_filtro_persistencia_temporal():
    from datetime import datetime, timedelta, timezone

    from src.domain.telemetria.entities import AlertaDispositivo
    from src.domain.telemetria.services import FiltroPersistenciaTemporalService
    from src.domain.telemetria.value_objects import SeveridadAlerta

    filtro = FiltroPersistenciaTemporalService(min_lecturas=2, min_segundos=3.0)
    t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    alerta_w = AlertaDispositivo(
        id=None,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Tensión baja 195V",
        disparada_en=t0,
    )

    # 1. 1ra lectura (t=0s) -> Transitorio: NO debe disparar alerta
    res1 = filtro.procesar_alerta("dev-1", alerta_w, ahora=t0)
    assert res1 is None

    # Caso A: Transitorio se recupera a t=1s (None alerta)
    res_rec = filtro.procesar_alerta("dev-1", None, ahora=t0 + timedelta(seconds=1))
    assert res_rec is None

    # Caso B: Vuelve a bajar la tensión a t=2s (nueva 1ra lectura tras recuperación)
    res_nuevo = filtro.procesar_alerta("dev-1", alerta_w, ahora=t0 + timedelta(seconds=2))
    assert res_nuevo is None

    # 2. 2da lectura consecutiva a t=3s -> Debe DISPARAR alerta (conteo = 2)
    res2 = filtro.procesar_alerta("dev-1", alerta_w, ahora=t0 + timedelta(seconds=3))
    assert res2 is not None
    assert res2.tipo_alerta == "BAJA_TENSION"
    assert res2.severidad == SeveridadAlerta.WARNING

    # 3. 3ra lectura continua a t=4s (mismo episodio) -> NO debe spamear
    res3 = filtro.procesar_alerta("dev-1", alerta_w, ahora=t0 + timedelta(seconds=4))
    assert res3 is None

    # 4. 4ta lectura a t=5s con escalamiento a CRITICAL -> Debe disparar alerta CRITICAL
    alerta_c = AlertaDispositivo(
        id=None,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.CRITICAL,
        mensaje="Tensión baja crítica 185V",
        disparada_en=t0 + timedelta(seconds=5),
    )
    res4 = filtro.procesar_alerta("dev-1", alerta_c, ahora=t0 + timedelta(seconds=5))
    assert res4 is not None
    assert res4.severidad == SeveridadAlerta.CRITICAL

    # 5. Limpieza de filtro
    filtro.limpiar()
    res_post_limpieza = filtro.procesar_alerta("dev-1", alerta_w, ahora=t0 + timedelta(seconds=10))
    assert res_post_limpieza is None
