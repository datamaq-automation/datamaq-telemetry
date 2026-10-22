"""tests/unit/test_domain.py."""

from datetime import datetime, timezone

import pytest

from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import (
    LecturaInstantanea,
    MedicionFase,
)
from src.domain.telemetria.exceptions import (
    FactorPotenciaInvalidoError,
    MacAddressInvalidaError,
    TensionInvalidaError,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService, CalculadoraPotenciaService
from src.domain.telemetria.value_objects import (
    AnaliticaCalidadEnergia,
    Corriente,
    EstadoFactorPotencia,
    EstadoTension,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
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


def test_calcular_corriente_neutro_fasorial():
    # 1. Sistema perfectamente equilibrado (I_R=I_S=I_T=100A, FP=1.0) -> I_N = 0
    in_eq = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(
        ir=100.0, is_=100.0, it=100.0, pr=22000.0, ps=22000.0, pt=22000.0, qr=0.0, qs=0.0, qt=0.0
    )
    assert in_eq is not None
    assert in_eq.amperios == 0.0

    # 2. Carga puramente monofásica en Fase R (100A) -> I_N = 100A
    in_mono = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(
        ir=100.0, is_=0.0, it=0.0, pr=22000.0, ps=0.0, pt=0.0, qr=0.0, qs=0.0, qt=0.0
    )
    assert in_mono is not None
    assert in_mono.amperios == 100.0

    # 3. Dos fases activas desfasadas 120° (80A y 90A) -> I_N ~ 85.44A
    in_dos_fases = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(
        ir=0.0, is_=80.0, it=90.0, pr=0.0, ps=17600.0, pt=19800.0, qr=0.0, qs=0.0, qt=0.0
    )
    assert in_dos_fases is not None
    assert 85.0 <= in_dos_fases.amperios <= 86.0

    # 4. Datos nulos o incompletos -> retorna None
    assert AnalizadorCalidadEnergiaService.calcular_corriente_neutro(None, 10.0, 10.0) is None


def test_calcular_tension_neutro():
    # 1. Sistema perfectamente equilibrado (VR=VS=VT=220V) -> V_N = 0.0
    vn_eq = AnalizadorCalidadEnergiaService.calcular_tension_neutro(
        vr=220.0, vs=220.0, vt=220.0, ir=1.0, is_=1.0, it=1.0
    )
    assert vn_eq == 0.0

    # 2. Desbalance de tensiones (VR=230V, VS=220V, VT=210V) -> V_N ~ 5.77V
    vn_desbal = AnalizadorCalidadEnergiaService.calcular_tension_neutro(
        vr=230.0, vs=220.0, vt=210.0, ir=1.0, is_=1.0, it=1.0
    )
    assert vn_desbal is not None
    assert vn_desbal == 5.77

    # 3. Faltan datos de fase -> retorna None
    assert AnalizadorCalidadEnergiaService.calcular_tension_neutro(None, 220.0, 220.0, 1.0, 1.0, 1.0) is None
    assert AnalizadorCalidadEnergiaService.calcular_tension_neutro(220.0, None, 220.0, 1.0, 1.0, 1.0) is None
    assert AnalizadorCalidadEnergiaService.calcular_tension_neutro(220.0, 220.0, None, 1.0, 1.0, 1.0) is None


def test_evaluar_alerta_ti_invertido():
    ahora = datetime.now(timezone.utc)

    # 1. Caso Normal (consumo positivo) -> Sin alertas
    lectura_normal = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
        fase_s=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
        fase_t=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
    )
    alertas_ok = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido("dev-1", lectura_normal)
    assert len(alertas_ok) == 0

    # 2. Caso TI Invertido en Fase S (I=40A, P=-8500W en instalación CONSUMO) -> Alerta
    lectura_invertida = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
        fase_s=MedicionFase(corriente=Corriente(40.0), potencia_activa=PotenciaActiva(-8500.0)),
        fase_t=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
    )
    alertas_inv = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
        "dev-1", lectura_invertida, tipo_instalacion="CONSUMO", fases_con_ti=["R", "S", "T"]
    )
    assert len(alertas_inv) == 1
    assert alertas_inv[0].tipo_alerta == "TI_INVERTIDO"
    assert "Fase S" in alertas_inv[0].mensaje
    assert alertas_inv[0].severidad == SeveridadAlerta.WARNING

    # 3. Caso Ruido residual en fase sin carga (I=1.2A, P=-10W) -> No dispara falsa alarma (menor a 5A)
    lectura_ruido = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(1.2), potencia_activa=PotenciaActiva(-10.0)),
        fase_s=MedicionFase(corriente=Corriente(40.0), potencia_activa=PotenciaActiva(8500.0)),
        fase_t=MedicionFase(corriente=Corriente(50.0), potencia_activa=PotenciaActiva(11000.0)),
    )
    alertas_ruido = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido("dev-1", lectura_ruido)
    assert len(alertas_ruido) == 0

    # 4. Caso Fase no instalada en dispositivo 2 TIs (Fase R no monitoreada) -> Ignorada
    alertas_no_ti = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
        "dev-2", lectura_invertida, tipo_instalacion="CONSUMO", fases_con_ti=["R", "T"]
    )
    assert len(alertas_no_ti) == 0  # Fase S no está en fases_con_ti

    # 5. Caso Instalación Fotovoltaica (GENERACION_FV) -> Potencia negativa permitida, sin alerta
    alertas_fv = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
        "dev-solar", lectura_invertida, tipo_instalacion="GENERACION_FV"
    )
    assert len(alertas_fv) == 0


def test_agregar_lecturas_en_intervalo():
    from datetime import datetime, timedelta, timezone

    from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import Corriente, PotenciaActiva, Tension

    t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    # 3 lecturas dentro del mismo bucket de 60 segundos (t=0s, t=20s, t=40s)
    l1 = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=t0,
        fase_r=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        potencia_activa_total=PotenciaActiva(6600.0),
    )
    l2 = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=t0 + timedelta(seconds=20),
        fase_r=MedicionFase(tension=Tension(230.0), corriente=Corriente(12.0), potencia_activa=PotenciaActiva(2760.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_t=MedicionFase(tension=Tension(210.0), corriente=Corriente(8.0), potencia_activa=PotenciaActiva(1680.0)),
        potencia_activa_total=PotenciaActiva(6640.0),
    )
    # 1 lectura en el siguiente bucket de 60 segundos (t=70s)
    l3 = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=t0 + timedelta(seconds=70),
        fase_r=MedicionFase(tension=Tension(225.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2250.0)),
        fase_s=MedicionFase(tension=Tension(225.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2250.0)),
        fase_t=MedicionFase(tension=Tension(225.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2250.0)),
        potencia_activa_total=PotenciaActiva(6750.0),
    )

    agregadas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo([l1, l2, l3], intervalo_segundos=60)
    assert len(agregadas) == 2

    # El bucket más reciente primero (t0 + 60s)
    b_reciente = agregadas[0]
    assert b_reciente.registrado_en == t0 + timedelta(seconds=60)
    assert b_reciente.fase_r.tension is not None
    assert b_reciente.fase_r.tension.voltios == 225.0

    # El bucket anterior (t0)
    b_anterior = agregadas[1]
    assert b_anterior.registrado_en == t0
    # VR promedio entre 220 y 230 -> 225
    assert b_anterior.fase_r.tension is not None
    assert b_anterior.fase_r.tension.voltios == 225.0
    # IR promedio entre 10 y 12 -> 11
    assert b_anterior.fase_r.corriente is not None
    assert b_anterior.fase_r.corriente.amperios == 11.0
    # P_tot promedio entre 6600 y 6640 -> 6620
    assert b_anterior.potencia_activa_total is not None
    assert b_anterior.potencia_activa_total.vatios == 6620.0


def test_politica_suscripcion_retencion_y_vigencia_pro():
    from datetime import datetime, timedelta, timezone

    from src.domain.telemetria.services import PoliticaSuscripcionService
    from src.domain.telemetria.value_objects import ModoFreeTier

    ahora = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Vigencia PRO: depende únicamente de si `ahora` es anterior o igual al vencimiento
    vencimiento = ahora + timedelta(days=30)
    assert PoliticaSuscripcionService.es_pro_vigente(vencimiento, ahora) is True
    assert PoliticaSuscripcionService.es_pro_vigente(vencimiento, ahora + timedelta(days=30)) is True
    assert PoliticaSuscripcionService.es_pro_vigente(vencimiento, ahora + timedelta(days=31)) is False
    assert PoliticaSuscripcionService.es_pro_vigente(None, ahora) is False

    # Políticas de Retención y Granularidad: PRO vs. único modo Free (PRIVADO_BASICO)
    assert PoliticaSuscripcionService.resolver_retencion_dias(True, ModoFreeTier.PRIVADO_BASICO) == 365
    assert PoliticaSuscripcionService.resolver_intervalo_minimo_segundos(True, ModoFreeTier.PRIVADO_BASICO) == 0

    assert PoliticaSuscripcionService.resolver_retencion_dias(False, ModoFreeTier.PRIVADO_BASICO) == 7
    assert PoliticaSuscripcionService.resolver_intervalo_minimo_segundos(False, ModoFreeTier.PRIVADO_BASICO) == 3600


def test_politica_suscripcion_compatibilidad_naive_aware_timezone():
    from datetime import datetime, timezone

    from src.domain.telemetria.services import PoliticaSuscripcionService

    ahora_aware = datetime.now(timezone.utc)
    venc_naive = datetime(2026, 12, 31, 23, 59, 59)
    venc_aware = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    ahora_naive = datetime(2026, 1, 1, 0, 0, 0)

    # Combinaciones naive vs aware
    assert PoliticaSuscripcionService.es_pro_vigente(venc_naive, ahora_aware) is True
    assert PoliticaSuscripcionService.es_pro_vigente(venc_aware, ahora_naive) is True
    assert PoliticaSuscripcionService.es_pro_vigente(venc_naive, ahora_naive) is True
    assert PoliticaSuscripcionService.es_pro_vigente(venc_aware, ahora_aware) is True

    # None handling
    assert PoliticaSuscripcionService.es_pro_vigente(None, ahora_aware) is False


def test_evaluar_alerta_tension_falta_fase_y_campos_enriquecidos():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
    from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
    from src.domain.telemetria.value_objects import SeveridadAlerta, Tension

    ahora = datetime.now(timezone.utc)

    # 1. Falta de fase (V < 50V) en Fase S
    lectura_corte = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(220.0)),
        fase_s=MedicionFase(tension=Tension(12.5)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_corte = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_corte)
    assert alerta_corte is not None
    assert alerta_corte.tipo_alerta == "FALTA_FASE"
    assert alerta_corte.severidad == SeveridadAlerta.CRITICAL
    assert alerta_corte.fase == "S"
    assert alerta_corte.valor_medido == 12.5
    assert alerta_corte.valor_umbral == 50.0
    assert alerta_corte.unidad == "V"
    assert alerta_corte.categoria == "SUMINISTRO"

    # 2. Subtensión contractual ENRE (195V) en Fase R
    lectura_sub = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(195.0)),
        fase_s=MedicionFase(tension=Tension(220.0)),
        fase_t=MedicionFase(tension=Tension(220.0)),
    )
    alerta_sub = AnalizadorCalidadEnergiaService.evaluar_alerta_tension("dev-1", lectura_sub)
    assert alerta_sub is not None
    assert alerta_sub.tipo_alerta == "BAJA_TENSION"
    assert alerta_sub.severidad == SeveridadAlerta.WARNING
    assert alerta_sub.fase == "R"
    assert alerta_sub.valor_medido == 195.0
    assert alerta_sub.valor_umbral == 198.0
    assert alerta_sub.unidad == "V"
    assert alerta_sub.categoria == "TENSION"


def test_evaluar_alerta_factor_potencia():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
    from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
    from src.domain.telemetria.value_objects import FactorPotencia, PotenciaActiva, SeveridadAlerta

    ahora = datetime.now(timezone.utc)

    # 1. Carga baja (<500W) -> No dispara alarma para evitar falsos positivos
    lectura_vacio = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(200.0),
        factor_potencia_total=FactorPotencia(0.60),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alerta_factor_potencia("dev-1", lectura_vacio) is None

    # 2. Carga en servicio (P=5000W) con FP=0.88 (Warning ENRE < 0.95)
    lectura_warning = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(5000.0),
        factor_potencia_total=FactorPotencia(0.88),
    )
    alerta_w = AnalizadorCalidadEnergiaService.evaluar_alerta_factor_potencia("dev-1", lectura_warning)
    assert alerta_w is not None
    assert alerta_w.tipo_alerta == "BAJO_FACTOR_POTENCIA"
    assert alerta_w.severidad == SeveridadAlerta.WARNING
    assert alerta_w.fase == "TOTAL"
    assert alerta_w.valor_medido == 0.88
    assert alerta_w.valor_umbral == 0.95
    assert alerta_w.categoria == "FACTOR_POTENCIA"

    # 3. Carga en servicio (P=5000W) con FP=0.75 (Critical < 0.85)
    lectura_critica = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(5000.0),
        factor_potencia_total=FactorPotencia(0.75),
    )
    alerta_c = AnalizadorCalidadEnergiaService.evaluar_alerta_factor_potencia("dev-1", lectura_critica)
    assert alerta_c is not None
    assert alerta_c.severidad == SeveridadAlerta.CRITICAL
    assert alerta_c.valor_medido == 0.75
    assert alerta_c.valor_umbral == 0.85


def test_evaluar_alertas_distorsion_armonica_tension():
    ahora = datetime.now(timezone.utc)

    # 1. Normal THD_V (<5.0%) -> Sin alertas
    lectura_normal = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=2.5),
        fase_s=MedicionFase(thd_v_porcentaje=3.1),
        fase_t=MedicionFase(thd_v_porcentaje=2.8),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_normal) == []

    # 2. Warning THD_V (5.0% < THD_V <= 8.0%) en Fase R
    lectura_warning = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=5.8),
        fase_s=MedicionFase(thd_v_porcentaje=3.0),
        fase_t=MedicionFase(thd_v_porcentaje=3.0),
    )
    alertas_w = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_warning)
    assert len(alertas_w) == 1
    assert alertas_w[0].tipo_alerta == "ALTO_THD_TENSION_WARNING"
    assert alertas_w[0].severidad == SeveridadAlerta.WARNING
    assert alertas_w[0].fase == "R"
    assert alertas_w[0].valor_medido == 5.8
    assert alertas_w[0].valor_umbral == 5.0
    assert alertas_w[0].categoria == "DISTORSION_ARMONICA"

    # 3. Critical THD_V (> 8.0%) en Fase S
    lectura_critica = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=3.0),
        fase_s=MedicionFase(thd_v_porcentaje=9.2),
        fase_t=MedicionFase(thd_v_porcentaje=3.0),
    )
    alertas_c = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_critica)
    assert len(alertas_c) == 1
    assert alertas_c[0].tipo_alerta == "ALTO_THD_TENSION_CRITICAL"
    assert alertas_c[0].severidad == SeveridadAlerta.CRITICAL
    assert alertas_c[0].fase == "S"
    assert alertas_c[0].valor_medido == 9.2
    assert alertas_c[0].valor_umbral == 8.0
    assert alertas_c[0].categoria == "DISTORSION_ARMONICA"


def test_evaluar_alertas_distorsion_armonica_corriente():
    ahora = datetime.now(timezone.utc)

    # 1. THD_I alto (25%) pero corriente baja (2A < 10A) -> No dispara para evitar falsos positivos en vacío
    lectura_vacio = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(2.0), thd_i_porcentaje=25.0),
        fase_s=MedicionFase(corriente=Corriente(2.0), thd_i_porcentaje=25.0),
        fase_t=MedicionFase(corriente=Corriente(2.0), thd_i_porcentaje=25.0),
    )
    assert AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_vacio) == []

    # 2. THD_I alto (22.5%) con corriente en carga (35A >= 10A) en Fase T
    lectura_carga = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(corriente=Corriente(30.0), thd_i_porcentaje=12.0),
        fase_s=MedicionFase(corriente=Corriente(30.0), thd_i_porcentaje=14.0),
        fase_t=MedicionFase(corriente=Corriente(35.0), thd_i_porcentaje=22.5),
    )
    alertas_i = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_carga)
    assert len(alertas_i) == 1
    assert alertas_i[0].tipo_alerta == "ALTO_THD_CORRIENTE"
    assert alertas_i[0].severidad == SeveridadAlerta.WARNING
    assert alertas_i[0].fase == "T"
    assert alertas_i[0].valor_medido == 22.5
    assert alertas_i[0].valor_umbral == 20.0
    assert alertas_i[0].categoria == "DISTORSION_ARMONICA"


def test_evaluar_alertas_riesgo_resonancia_capacitores():
    ahora = datetime.now(timezone.utc)

    # 1. THD_V elevado (4.5% >= 4.0%) y FP cercano a 1.0 (FP=0.99 >= 0.98) -> Resonancia
    lectura_resonancia = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=4.5),
        fase_s=MedicionFase(thd_v_porcentaje=4.2),
        fase_t=MedicionFase(thd_v_porcentaje=4.1),
        factor_potencia_total=FactorPotencia(0.99),
    )
    alertas_res = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_resonancia)
    assert any(a.tipo_alerta == "RIESGO_RESONANCIA_CAPACITORES" for a in alertas_res)
    alerta_res = next(a for a in alertas_res if a.tipo_alerta == "RIESGO_RESONANCIA_CAPACITORES")
    assert alerta_res.severidad == SeveridadAlerta.WARNING
    assert alerta_res.valor_medido == 4.5
    assert alerta_res.valor_umbral == 4.0
    assert alerta_res.categoria == "DISTORSION_ARMONICA"

    # 2. THD_V normal (2.5%) con FP=0.99 -> No dispara resonancia
    lectura_normal_fp = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=2.5),
        fase_s=MedicionFase(thd_v_porcentaje=2.5),
        fase_t=MedicionFase(thd_v_porcentaje=2.5),
        factor_potencia_total=FactorPotencia(0.99),
    )
    alertas_normal = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura_normal_fp)
    assert not any(a.tipo_alerta == "RIESGO_RESONANCIA_CAPACITORES" for a in alertas_normal)


def test_dimensionador_calculo_potencia_compensacion():
    # Caso 1: P=100 kW, FP_actual=0.80, FP_objetivo=0.96
    # tan(arccos(0.80)) = 0.75, tan(arccos(0.96)) = 0.29166667
    # Qc = 100 * (0.75 - 0.29166667) = 45.83 kVAr
    qc = DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.80, 0.96)
    assert qc == 45.83

    # Caso 2: FP_actual >= FP_objetivo -> No requiere compensación (0.0)
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.98, 0.96) == 0.0
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(50.0, 1.0, 0.96) == 0.0
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(50.0, 0.96, 0.96) == 0.0

    # Caso 3: Entradas inválidas o nulas
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(None, 0.80) is None
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, None) is None
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(0.0, 0.80) is None
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(-50.0, 0.80) is None
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, -0.5) is None
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 1.2) is None


def test_dimensionador_calculo_potencia_compensacion_con_q_reactiva_capacitiva():
    """Si Q es capacitivo (<=0), no se recomienda más compensación."""
    # Q capacitivo: no recomendar banco aunque FP sea bajo
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.80, q_reactiva_kvar=-40.0) == 0.0
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.85, q_reactiva_kvar=-50.0) == 0.0

    # Q=0 (límite): también retorna 0.0
    assert DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.80, q_reactiva_kvar=0.0) == 0.0

    # Q inductivo (>0): comportamiento sin cambios, sigue calculando Qc
    qc_inductivo = DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.80, q_reactiva_kvar=40.0)
    assert qc_inductivo == 45.83

    # Sin pasar Q: comportamiento sin cambios (compatibilidad hacia atrás)
    qc_sin_q = DimensionadorCompensacionService.calcular_potencia_compensacion(100.0, 0.80)
    assert qc_sin_q == 45.83


def test_dimensionador_sugerencia_banco_comercial():
    # Qc = 45.83 -> Banco sugerido comercial más cercano = 50.0 kVAr
    assert DimensionadorCompensacionService.sugerir_banco_comercial(45.83) == 50.0
    assert DimensionadorCompensacionService.sugerir_banco_comercial(11.2) == 12.5
    assert DimensionadorCompensacionService.sugerir_banco_comercial(22.0) == 25.0
    assert DimensionadorCompensacionService.sugerir_banco_comercial(2.0) == 2.5
    assert DimensionadorCompensacionService.sugerir_banco_comercial(950.0) == 1000.0

    # Banco > 1000 kVAr -> Múltiplo superior de 50 kVAr
    assert DimensionadorCompensacionService.sugerir_banco_comercial(1020.0) == 1050.0

    # Valores nulos o no positivos
    assert DimensionadorCompensacionService.sugerir_banco_comercial(None) is None
    assert DimensionadorCompensacionService.sugerir_banco_comercial(0.0) is None
    assert DimensionadorCompensacionService.sugerir_banco_comercial(-10.0) is None


def test_dimensionador_escalones_sugeridos():
    # Banco pequeño <= 25 kVAr -> Escalón único
    assert DimensionadorCompensacionService.calcular_escalones_sugeridos(10.0) == [10.0]
    assert DimensionadorCompensacionService.calcular_escalones_sugeridos(22.0) == [25.0]

    # Banco mediano (50 kVAr) -> Pasos de 12.5 kVAr: [12.5, 12.5, 12.5, 12.5]
    escalones_50 = DimensionadorCompensacionService.calcular_escalones_sugeridos(45.83, paso_modular_kvar=12.5)
    assert escalones_50 == [12.5, 12.5, 12.5, 12.5]
    assert sum(escalones_50) == 50.0

    # Banco grande (100 kVAr) -> Pasos de 25 kVAr: [25.0, 25.0, 25.0, 25.0]
    escalones_100 = DimensionadorCompensacionService.calcular_escalones_sugeridos(95.0)
    assert escalones_100 == [25.0, 25.0, 25.0, 25.0]
    assert sum(escalones_100) == 100.0

    # Casos nulos
    assert DimensionadorCompensacionService.calcular_escalones_sugeridos(None) == []
    assert DimensionadorCompensacionService.calcular_escalones_sugeridos(0.0) == []


def test_dimensionador_estimacion_penalizacion_ars():
    # P=100 kW, FP=0.80 (<0.95 penalizado)
    # factor_recargo = (0.95 / 0.80 - 1) = 0.1875
    # costo_base = 100 * 720 * 95 + 100 * 1500 = 6,840,000 + 150,000 = 6,990,000 ARS
    # recargo = 6,990,000 * 0.1875 = 1,310,625.0 ARS
    penalizacion = DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(
        potencia_activa_kw=100.0,
        fp_actual=0.80,
        horas_mes=720.0,
        tarifa_kwh_ars=95.0,
        cargo_potencia_kw_ars=1500.0,
    )
    assert penalizacion == 1310625.0

    # FP >= 0.95 -> 0.0 (Sin penalización)
    assert (
        DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(
            potencia_activa_kw=100.0,
            fp_actual=0.95,
        )
        == 0.0
    )
    assert (
        DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(
            potencia_activa_kw=100.0,
            fp_actual=0.99,
        )
        == 0.0
    )

    # Entradas inválidas
    assert DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(None, 0.80) is None
    assert DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(100.0, None) is None
    assert DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(0.0, 0.80) is None


def test_dimensionador_sobrecompensacion_y_evaluacion():
    # es_sobrecompensacion_sostenida
    assert DimensionadorCompensacionService.es_sobrecompensacion_sostenida(-5.0) is True
    assert DimensionadorCompensacionService.es_sobrecompensacion_sostenida(0.0) is True
    assert DimensionadorCompensacionService.es_sobrecompensacion_sostenida(0.1) is False
    assert DimensionadorCompensacionService.es_sobrecompensacion_sostenida(None) is False

    # evaluar_compensacion con sobrecompensacion sostenida (Q_max <= 0)
    qc, banco, escalones, sobrecomp = DimensionadorCompensacionService.evaluar_compensacion(
        potencia_activa_kw=100.0,
        fp_actual=0.88,
        q_reactiva_kvar=-10.0,
        q_max_kvar=0.0,
    )
    assert sobrecomp is True
    assert qc == 0.0
    assert banco is None
    assert escalones == []

    # evaluar_compensacion con régimen inductivo normal
    qc, banco, escalones, sobrecomp = DimensionadorCompensacionService.evaluar_compensacion(
        potencia_activa_kw=100.0,
        fp_actual=0.80,
        q_reactiva_kvar=50.0,
        q_max_kvar=60.0,
    )
    assert sobrecomp is False
    assert qc is not None and qc > 0.0
    assert banco is not None
    assert len(escalones) > 0


def test_calculo_desbalance_corriente():
    # Balanceado
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(100.0, 100.0, 100.0) == 0.0

    # Desbalanceado: I_prom = 100.0, desv_max = 10.0 -> (10/100)*100 = 10.0%
    iur = AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(110.0, 100.0, 90.0)
    assert iur == 10.0

    # Sin carga el IUR no es "0% de desbalance", es no medible
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(0.0, 0.0, 0.0) is None

    # Incompleto
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(100.0, None, 100.0) is None

    # Carga despreciable: el indicador se satura con ruido y no describe nada.
    # Caso real medido: R=0.9 A con S y T en miliamperes daba 170% de "desbalance".
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(0.9, 0.05, 0.05) is None

    # Justo por encima del umbral sí se reporta
    assert AnalizadorCalidadEnergiaService.calcular_desbalance_corriente(20.0, 10.0, 10.0) == 50.0


def test_determinar_estado_fp():
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.98) == EstadoFactorPotencia.OPTIMO
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.96) == EstadoFactorPotencia.OPTIMO
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.955) == EstadoFactorPotencia.ADVERTENCIA
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.95) == EstadoFactorPotencia.ADVERTENCIA
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.94) == EstadoFactorPotencia.PENALIZADO
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(0.80) == EstadoFactorPotencia.PENALIZADO
    # Sin FP medido no se afirma que sea óptimo
    assert AnalizadorCalidadEnergiaService.determinar_estado_fp(None) == EstadoFactorPotencia.SIN_DATOS


def test_determinar_estado_tension():
    # Tensiones normales en banda 198V - 242V
    assert AnalizadorCalidadEnergiaService.determinar_estado_tension(220.0, 225.0, 218.0) == EstadoTension.NORMAL

    # Subtensión (< 198V)
    assert AnalizadorCalidadEnergiaService.determinar_estado_tension(195.0, 220.0, 220.0) == EstadoTension.SUBTENSION

    # Sobretensión (> 242V)
    assert AnalizadorCalidadEnergiaService.determinar_estado_tension(220.0, 245.0, 220.0) == EstadoTension.SOBRETENSION

    # Sin lecturas: un medidor caído no está reportando "tensión normal"
    assert AnalizadorCalidadEnergiaService.determinar_estado_tension(None, None, None) == EstadoTension.SIN_DATOS


def test_calcular_analitica_completa():
    ahora = datetime.now(timezone.utc)

    # 1. Caso con compensación requerida y penalización
    lectura_baja_calidad = LecturaInstantanea(
        id=1,
        dispositivo_id="dev-100",
        registrado_en=ahora,
        fase_r=MedicionFase(
            tension=Tension(220.0), corriente=Corriente(150.0), potencia_activa=PotenciaActiva(33333.3)
        ),
        fase_s=MedicionFase(
            tension=Tension(215.0), corriente=Corriente(155.0), potencia_activa=PotenciaActiva(33333.3)
        ),
        fase_t=MedicionFase(
            tension=Tension(225.0), corriente=Corriente(145.0), potencia_activa=PotenciaActiva(33333.4)
        ),
        potencia_activa_total=PotenciaActiva(100000.0),  # 100 kW
        factor_potencia_total=FactorPotencia(0.80),
        desbalance_tension_porcentaje=2.27,
    )

    analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura_baja_calidad)

    assert isinstance(analitica, AnaliticaCalidadEnergia)
    assert analitica.requiere_compensacion is True
    assert analitica.potencia_reactiva_a_compensar_kvar == 45.83
    assert analitica.banco_sugerido_kvar == 50.0
    assert analitica.penalizacion_estimada_ars is not None and analitica.penalizacion_estimada_ars > 0
    assert analitica.desbalance_tension_porcentaje == 2.27
    assert analitica.desbalance_corriente_porcentaje is not None
    assert analitica.estado_fp == EstadoFactorPotencia.PENALIZADO
    assert analitica.estado_tension == EstadoTension.NORMAL

    # 2. Caso óptimo sin compensación requerida
    lectura_optima = LecturaInstantanea(
        id=2,
        dispositivo_id="dev-101",
        registrado_en=ahora,
        fase_r=MedicionFase(tension=Tension(220.0), corriente=Corriente(100.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(100.0)),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(100.0)),
        potencia_activa_total=PotenciaActiva(60000.0),  # 60 kW
        factor_potencia_total=FactorPotencia(0.98),
        desbalance_tension_porcentaje=0.0,
    )

    analitica_optima = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura_optima)

    assert analitica_optima.requiere_compensacion is False
    assert analitica_optima.potencia_reactiva_a_compensar_kvar == 0.0
    assert analitica_optima.banco_sugerido_kvar is None
    assert analitica_optima.penalizacion_estimada_ars == 0.0
    assert analitica_optima.desbalance_tension_porcentaje == 0.0
    assert analitica_optima.desbalance_corriente_porcentaje == 0.0
    assert analitica_optima.estado_fp == EstadoFactorPotencia.OPTIMO
    assert analitica_optima.estado_tension == EstadoTension.NORMAL


def test_calculadora_potencia_aparente_es_v_por_i():
    calc = CalculadoraPotenciaService
    # Caso real medido en el SmartPlus: V=227.7, I=0.9
    assert calc.calcular_potencia_aparente(227.7, 0.9) == 204.93
    # Cero es una medición válida de "sin carga", no un dato ausente
    assert calc.calcular_potencia_aparente(220.0, 0.0) == 0.0
    assert calc.calcular_potencia_aparente(None, 0.9) is None
    assert calc.calcular_potencia_aparente(227.7, None) is None
    # V e I son magnitudes RMS: un signo indicaría dato corrupto, no dirección
    assert calc.calcular_potencia_aparente(-227.7, 0.9) == 204.93


def test_calculadora_factor_potencia_acota_y_preserva_signo():
    calc = CalculadoraPotenciaService
    assert calc.calcular_factor_potencia(147.0, 204.93) == 0.72
    # Sin potencia aparente el FP es indefinido, no óptimo
    assert calc.calcular_factor_potencia(147.0, 0.0) is None
    assert calc.calcular_factor_potencia(None, 204.93) is None
    assert calc.calcular_factor_potencia(147.0, None) is None
    # P negativo = exportación o TI invertido
    assert calc.calcular_factor_potencia(-147.0, 204.93) == -0.72


def test_calculadora_factor_potencia_no_rompe_el_value_object():
    """V·I sobre valores redondeados por el firmware puede quedar por debajo de |P|.

    Sin acotar, el cociente supera 1 y `FactorPotencia` lanza, tumbando la ingesta entera.
    """
    fp = CalculadoraPotenciaService.calcular_factor_potencia(250.0, 200.0)
    assert fp == 1.0
    assert FactorPotencia(valor=fp).valor == 1.0

    fp_neg = CalculadoraPotenciaService.calcular_factor_potencia(-250.0, 200.0)
    assert fp_neg == -1.0
    assert FactorPotencia(valor=fp_neg).valor == -1.0


def test_calculadora_potencia_aparente_total():
    calc = CalculadoraPotenciaService
    assert calc.calcular_potencia_aparente_total(204.93, 10.0, 5.07) == 220.0
    assert calc.calcular_potencia_aparente_total(204.93, None, None) == 204.93
    assert calc.calcular_potencia_aparente_total(None, None, None) is None


def test_calcular_analitica_completa_sin_factor_potencia():
    """El caso que producía el badge «ÓPTIMO» junto a un guion en el dashboard."""
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 1, 23, 20, tzinfo=timezone.utc),
        fase_r=MedicionFase(tension=Tension(voltios=227.7)),
        fase_s=MedicionFase(tension=Tension(voltios=227.4)),
        fase_t=MedicionFase(tension=Tension(voltios=228.5)),
        factor_potencia_total=None,
    )

    analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura)

    assert analitica.estado_fp == EstadoFactorPotencia.SIN_DATOS
    assert analitica.requiere_compensacion is False


def test_agregacion_usa_v_por_i_y_no_hypot():
    """La agregación comparte definición con `raw`: S = V̄·Ī, no hypot(P,Q).

    Antes una consulta `raw` devolvía null donde la agregada devolvía hypot, es decir
    dos definiciones distintas de potencia aparente en la misma API.
    """
    base = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)

    def _lectura(segundo: int) -> LecturaInstantanea:
        fase = MedicionFase(
            tension=Tension(voltios=200.0),
            corriente=Corriente(amperios=2.0),
            potencia_activa=PotenciaActiva(vatios=300.0),
            potencia_reactiva=PotenciaReactiva(var=400.0),
        )
        return LecturaInstantanea(
            id=None,
            dispositivo_id="dev-1",
            registrado_en=base.replace(second=segundo),
            fase_r=fase,
            fase_s=fase,
            fase_t=fase,
        )

    agregadas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo(
        [_lectura(0), _lectura(30)], intervalo_segundos=60
    )

    assert len(agregadas) == 1
    fase_r = agregadas[0].fase_r
    assert fase_r.potencia_aparente is not None
    # V·I = 200 * 2 = 400 VA. hypot(300, 400) habría dado 500 VA.
    assert fase_r.potencia_aparente.va == 400.0
    assert fase_r.factor_potencia is not None
    assert fase_r.factor_potencia.valor == 0.75


def test_analitica_no_dimensiona_compensacion_con_carga_despreciable():
    """Con 148 W de standby la analítica llegaba a estimar una multa de ARS 4.774."""
    fase = MedicionFase(
        tension=Tension(voltios=227.7),
        corriente=Corriente(amperios=0.9),
        potencia_activa=PotenciaActiva(vatios=147.0),
        potencia_aparente=PotenciaAparente(va=204.93),
        factor_potencia=FactorPotencia(valor=0.72),
    )
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 1, 23, 20, tzinfo=timezone.utc),
        fase_r=fase,
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios=148.0),
        factor_potencia_total=FactorPotencia(valor=0.65),
    )

    analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura)

    assert analitica.requiere_compensacion is False
    assert analitica.banco_sugerido_kvar is None
    assert analitica.penalizacion_estimada_ars is None
    # El estado del FP sí se reporta: la medición es real aunque no se dimensione nada
    assert analitica.estado_fp == EstadoFactorPotencia.PENALIZADO


def test_analitica_dimensiona_compensacion_con_carga_facturable():
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 1, 23, 20, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios=15000.0),
        factor_potencia_total=FactorPotencia(valor=0.80),
    )

    analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura)

    assert analitica.requiere_compensacion is True
    assert analitica.banco_sugerido_kvar is not None
    assert analitica.penalizacion_estimada_ars is not None


def test_mensajes_thd_tension_son_umbral_interno_no_normativo():
    """Los umbrales de THD_V son internos (addendum 2026-10-10): ningún mensaje afirma norma ni cumplimiento."""
    ahora = datetime.now(timezone.utc)
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=ahora,
        fase_r=MedicionFase(thd_v_porcentaje=5.8),
        fase_s=MedicionFase(thd_v_porcentaje=9.2),
        fase_t=MedicionFase(thd_v_porcentaje=3.0),
    )

    alertas = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica("dev-1", lectura)

    assert len(alertas) == 2
    for alerta in alertas:
        assert "umbral interno" in alerta.mensaje
        assert "referencia: IEEE 519-2014" in alerta.mensaje
        assert "Límite IEEE 519" not in alerta.mensaje
        assert "Límite IEC" not in alerta.mensaje
        assert "normativ" not in alerta.mensaje.lower()
        assert "normativ" not in (alerta.observaciones or "").lower()
