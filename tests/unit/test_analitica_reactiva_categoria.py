"""tests/unit/test_analitica_reactiva_categoria.py — Tests unitarios para exenciones de penalización por reactiva."""

from datetime import datetime, timezone

from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.analizador_calidad_metrologica import AnalizadorMetrologicoService
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    Tension,
)

AHORA = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def _crear_lectura(fp: float = 0.80, potencia_w: float = 2000.0) -> LecturaInstantanea:
    fase = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(10.0),
        potencia_activa=PotenciaActiva(potencia_w),
        factor_potencia=FactorPotencia(fp),
    )
    return LecturaInstantanea(
        id=1,
        dispositivo_id="disp-1",
        registrado_en=AHORA,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
        potencia_activa_total=PotenciaActiva(potencia_w * 3),
        factor_potencia_total=FactorPotencia(fp),
    )


def test_analitica_reactiva_exenta_monofasica_t1r():
    disp = Dispositivo(
        id="disp-1",
        device_uid=MacAddress("28:12:d2:af:b1:cf"),
        nombre="Medidor Hogar",
        categoria_tarifaria="T1-R",
        penalizacion_reactiva_aplica=False,
    )
    lectura = _crear_lectura(fp=0.70)

    analitica = AnalizadorMetrologicoService.calcular_analitica_completa(
        lectura=lectura,
        dispositivo=disp,
    )

    assert analitica.requiere_compensacion is False
    assert analitica.penalizacion_estimada_ars is None
    assert analitica.motivo_abstencion == "TARIFA_SIN_CARGO_REACTIVA"


def test_analitica_reactiva_aplica_para_t2():
    disp = Dispositivo(
        id="disp-2",
        device_uid=MacAddress("51:04:8a:93:f1:f3"),
        nombre="SmartPlus Industrial",
        categoria_tarifaria="T2",
        penalizacion_reactiva_aplica=True,
    )
    lectura = _crear_lectura(fp=0.80, potencia_w=5000.0)

    analitica = AnalizadorMetrologicoService.calcular_analitica_completa(
        lectura=lectura,
        dispositivo=disp,
    )

    assert analitica.requiere_compensacion is True
    assert analitica.penalizacion_estimada_ars is None
    assert analitica.motivo_abstencion is None


def test_analitica_reactiva_t1g_monofasico_no_esta_exenta():
    """Hallazgo de la investigación de D-11: un T1-G (comercio, consorcio) con
    medidor monofásico que registra reactiva SÍ está alcanzado por el cargo —
    la exención es por categoría T1-R, no por cantidad de fases. Antes de esta
    corrección, `es_monofasico` eximía a este caso por error."""
    disp = Dispositivo(
        id="disp-1",
        device_uid=MacAddress("28:12:d2:af:b1:cf"),
        nombre="Comercio Monofásico",
        categoria_tarifaria="T1-G",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R",
    )
    lectura = _crear_lectura(fp=0.70)

    analitica = AnalizadorMetrologicoService.calcular_analitica_completa(
        lectura=lectura,
        dispositivo=disp,
    )

    assert analitica.motivo_abstencion is None
    assert analitica.requiere_compensacion is True
