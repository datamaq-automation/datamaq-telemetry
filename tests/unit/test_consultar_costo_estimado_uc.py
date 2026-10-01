"""tests/unit/test_consultar_costo_estimado_uc.py — Caso de uso ConsultarCostoEstimadoUseCase.

Cubre el componente de energía (kWh en vivo x $/kWh de la última factura) y que el componente de
potencia quede siempre "s/d" explícito (no existe tracking de demanda máxima en vivo todavía, ver
`specs/costo-estimado-periodo-en-curso.md`).
"""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from src.application.use_cases.consultar_costo_estimado import ConsultarCostoEstimadoUseCase
from src.domain.sge.entities import FacturaDistribuidora
from src.domain.telemetria.entities import EnergiaAgregada, NodoUnifilar, Planta
from src.domain.telemetria.value_objects import TipoNodoUnifilar

PLANTA_ID = "planta-x"


def _factura_energia(periodo: str, valor_kwh_promedio: float) -> FacturaDistribuidora:
    return FacturaDistribuidora(
        id=f"{PLANTA_ID}-{periodo}-energia",
        planta_id=PLANTA_ID,
        periodo=periodo,
        proveedor="CAMMESA",
        tipo_dato="energia",
        numero_factura="1",
        importe_total_ars=valor_kwh_promedio * 1000.0,
        energia_activa_total_kwh=1000.0,
        importe_energia_ars=valor_kwh_promedio * 1000.0,
    )


def _factura_potencia(
    periodo: str,
    importe_potencia_ars: float,
    contratada_punta: float = 800.0,
    contratada_fp: float = 850.0,
    adquirida_punta: float = 800.0,
    adquirida_fp: float = 850.0,
) -> FacturaDistribuidora:
    return FacturaDistribuidora(
        id=f"{PLANTA_ID}-{periodo}-potencia",
        planta_id=PLANTA_ID,
        periodo=periodo,
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="2",
        importe_total_ars=importe_potencia_ars,
        importe_potencia_ars=importe_potencia_ars,
        potencia_contratada_punta_kw=contratada_punta,
        potencia_contratada_fuera_punta_kw=contratada_fp,
        potencia_adquirida_punta_kw=adquirida_punta,
        potencia_adquirida_fuera_punta_kw=adquirida_fp,
    )


def _nodo_tgbt() -> NodoUnifilar:
    return NodoUnifilar(
        id="tgbt-1",
        planta_id=PLANTA_ID,
        nombre="TGBT",
        tipo=TipoNodoUnifilar.TGBT,
        tension_nominal_v=380.0,
        device_id="dev-1",
    )


def _repo(facturas: list[FacturaDistribuidora], nodos: list[NodoUnifilar]) -> MagicMock:
    repo = MagicMock()
    repo.obtener_planta_por_id.return_value = Planta(id=PLANTA_ID, organizacion_id="org-x", nombre="Planta X")
    repo.obtener_nodos_unifilar.return_value = nodos
    repo.obtener_facturas_planta.return_value = facturas
    return repo


def _use_case(facturas: list[FacturaDistribuidora], nodos: list[NodoUnifilar]) -> ConsultarCostoEstimadoUseCase:
    return ConsultarCostoEstimadoUseCase(
        repo_organizaciones=_repo(facturas, nodos),
        repo_telemetria=MagicMock(),
        consultar_telemetria=MagicMock(),
    )


def _mockear_kwh_mes_actual(kwh: float | None) -> tuple[MagicMock, list[EnergiaAgregada]]:
    """``calcular_resumen`` devuelve (potencia_sumada, energia_sumada); acá solo importa la 2da."""
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().replace(day=1)
    energia_sumada = [EnergiaAgregada(periodo=hoy, energia_activa_neta_kwh=kwh)] if kwh is not None else []
    return MagicMock(), energia_sumada


def test_costo_energia_es_kwh_en_vivo_por_valor_promedio_de_la_ultima_factura():
    use_case = _use_case([_factura_energia("2026-08", valor_kwh_promedio=2.0)], [_nodo_tgbt()])

    with patch(
        "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
        return_value=_mockear_kwh_mes_actual(500.0),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.kwh_consumido_periodo_actual == 500.0
    assert resultado.valor_energia_ars_kwh_promedio == 2.0
    assert resultado.costo_energia_ars == 1000.0
    assert resultado.periodo_factura_origen == "2026-08"


def test_potencia_siempre_sin_dato_explicito():
    use_case = _use_case([_factura_energia("2026-08", valor_kwh_promedio=2.0)], [_nodo_tgbt()])

    with patch(
        "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
        return_value=_mockear_kwh_mes_actual(500.0),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.costo_potencia_ars is None
    assert resultado.motivo_potencia_sin_dato == "demanda_maxima_no_disponible"


def test_sin_factura_de_energia_costo_es_sin_dato_no_cero():
    use_case = _use_case([], [_nodo_tgbt()])

    with patch(
        "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
        return_value=_mockear_kwh_mes_actual(500.0),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.valor_energia_ars_kwh_promedio is None
    assert resultado.costo_energia_ars is None


def test_energia_registrada_de_la_distribuidora_no_alimenta_el_costo():
    """D4 (decisión 2026-09-28): la energía registrada viaja en el documento de potencia de
    EDELAP y no es energía facturada; sin documento de energía el costo sigue en "s/d"."""
    potencia_con_registrada = FacturaDistribuidora(
        id=f"{PLANTA_ID}-2024-11-potencia",
        planta_id=PLANTA_ID,
        periodo="2024-11",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="0020-01988580",
        importe_total_ars=21031736.78,
        energia_registrada_punta_kwh=68310.0,
        energia_registrada_resto_kwh=187506.0,
        energia_registrada_valle_kwh=59994.0,
        energia_registrada_total_kwh=315810.0,
    )
    use_case = _use_case([potencia_con_registrada], [_nodo_tgbt()])

    with patch(
        "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
        return_value=_mockear_kwh_mes_actual(500.0),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.valor_energia_ars_kwh_promedio is None
    assert resultado.costo_energia_ars is None


def test_sin_nodos_no_hay_dato_de_kwh_en_vivo():
    use_case = _use_case([_factura_energia("2026-08", valor_kwh_promedio=2.0)], [])

    resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.kwh_consumido_periodo_actual is None
    assert resultado.costo_energia_ars is None


def test_aviso_tarifa_desactualizada_si_paso_mas_de_un_ciclo_de_facturacion():
    periodo_viejo = "2020-01"
    use_case = _use_case([_factura_energia(periodo_viejo, valor_kwh_promedio=2.0)], [_nodo_tgbt()])

    with patch(
        "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
        return_value=_mockear_kwh_mes_actual(500.0),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.aviso_tarifa_desactualizada is True


def test_sin_aviso_de_tarifa_desactualizada_sin_facturas():
    use_case = _use_case([], [])

    resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.aviso_tarifa_desactualizada is False


def test_periodo_actual_tiene_formato_anio_mes():
    use_case = _use_case([], [])

    resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert len(resultado.periodo_actual) == 7
    assert resultado.periodo_actual[4] == "-"


def test_costo_potencia_calculado_sin_exceso():
    # 800 kW punta + 850 kW fuera punta = 1650 kW total. Importe = 1_650_000 -> tarifa = 1000 $/kW
    f_pot = _factura_potencia("2026-08", importe_potencia_ars=1_650_000.0)
    f_ene = _factura_energia("2026-08", valor_kwh_promedio=2.0)
    use_case = _use_case([f_ene, f_pot], [_nodo_tgbt()])

    from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import DemandaCuartohoraria

    with (
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
            return_value=_mockear_kwh_mes_actual(500.0),
        ),
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_demanda_cuartohoraria",
            return_value=DemandaCuartohoraria(
                potencia_adquirida_punta_kw=700.0,
                potencia_adquirida_fuera_punta_kw=800.0,
            ),
        ),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.costo_potencia_ars == 1_650_000.0
    assert resultado.motivo_potencia_sin_dato is None


def test_costo_potencia_calculado_con_exceso():
    # Base: 800 kW punta + 850 kW fp = 1650 kW a 1000 $/kW -> cargo_base = 1_650_000
    # Demanda medida: punta = 900 (exceso 100), fp = 950 (exceso 100) -> recargo exceso = 200 * 1000 = 200_000
    # Total esperado = 1_850_000
    f_pot = _factura_potencia("2026-08", importe_potencia_ars=1_650_000.0)
    f_ene = _factura_energia("2026-08", valor_kwh_promedio=2.0)
    use_case = _use_case([f_ene, f_pot], [_nodo_tgbt()])

    from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import DemandaCuartohoraria

    with (
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
            return_value=_mockear_kwh_mes_actual(500.0),
        ),
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_demanda_cuartohoraria",
            return_value=DemandaCuartohoraria(
                potencia_adquirida_punta_kw=900.0,
                potencia_adquirida_fuera_punta_kw=950.0,
            ),
        ),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.costo_potencia_ars == 1_850_000.0
    assert resultado.motivo_potencia_sin_dato is None


def test_costo_potencia_sin_telemetria_queda_sin_dato():
    f_pot = _factura_potencia("2026-08", importe_potencia_ars=1_650_000.0)
    f_ene = _factura_energia("2026-08", valor_kwh_promedio=2.0)
    use_case = _use_case([f_ene, f_pot], [_nodo_tgbt()])

    from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import DemandaCuartohoraria

    with (
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_resumen",
            return_value=_mockear_kwh_mes_actual(500.0),
        ),
        patch(
            "src.application.use_cases.consultar_costo_estimado.calcular_demanda_cuartohoraria",
            return_value=DemandaCuartohoraria(
                potencia_adquirida_punta_kw=None,
                potencia_adquirida_fuera_punta_kw=None,
            ),
        ),
    ):
        resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.costo_potencia_ars is None
    assert resultado.motivo_potencia_sin_dato == "demanda_maxima_no_disponible"
