"""tests/unit/test_consultar_balance_energia_uc.py — Caso de uso ConsultarBalanceEnergiaUseCase.

No existía cobertura de este caso de uso (solo del servicio de dominio en
`test_balance_energia_sge.py`). Cubre puntualmente el fallback a la factura de la
distribuidora más reciente cuando no se pasa `energia_padre_kwh` explícito.
"""

from unittest.mock import MagicMock

from src.application.use_cases.consultar_balance_energia import ConsultarBalanceEnergiaUseCase
from src.domain.sge.entities import FacturaDistribuidora
from src.domain.telemetria.entities import Planta

PLANTA_ID = "planta-x"


def _factura(periodo: str, energia_punta: float) -> FacturaDistribuidora:
    return FacturaDistribuidora(
        id=f"{PLANTA_ID}-{periodo}",
        planta_id=PLANTA_ID,
        periodo=periodo,
        distribuidora="EDELAP",
        numero_factura="1",
        tarifa="T5M12",
        dias_facturados=30,
        energia_activa_punta_kwh=energia_punta,
        energia_activa_resto_kwh=0.0,
        energia_activa_valle_kwh=0.0,
        potencia_contratada_punta_kw=100.0,
        potencia_contratada_fuera_punta_kw=100.0,
        potencia_adquirida_punta_kw=100.0,
        potencia_adquirida_fuera_punta_kw=100.0,
        importe_potencia_ars=0.0,
        importe_energia_ars=0.0,
        importe_total_ars=0.0,
    )


def _repo(facturas: list[FacturaDistribuidora]) -> MagicMock:
    repo = MagicMock()
    repo.obtener_planta_por_id.return_value = Planta(id=PLANTA_ID, organizacion_id="org-x", nombre="Planta X")
    repo.obtener_nodos_unifilar.return_value = []
    repo.obtener_facturas_planta.return_value = facturas
    return repo


def test_sin_energia_padre_explicita_usa_la_factura_mas_reciente():
    repo = _repo([_factura("2026-08", 1000.0)])
    use_case = ConsultarBalanceEnergiaUseCase(repo_organizaciones=repo)

    resultado = use_case.ejecutar(planta_id=PLANTA_ID, energias_hijos_kwh=[900.0])

    assert resultado.energia_padre_kwh == 1000.0


def test_sin_energia_padre_explicita_y_sin_facturas_usa_cero():
    repo = _repo([])
    use_case = ConsultarBalanceEnergiaUseCase(repo_organizaciones=repo)

    resultado = use_case.ejecutar(planta_id=PLANTA_ID)

    assert resultado.energia_padre_kwh == 0.0


def test_energia_padre_explicita_tiene_prioridad_sobre_la_factura():
    repo = _repo([_factura("2026-08", 1000.0)])
    use_case = ConsultarBalanceEnergiaUseCase(repo_organizaciones=repo)

    resultado = use_case.ejecutar(planta_id=PLANTA_ID, energia_padre_kwh=500.0, energias_hijos_kwh=[400.0])

    assert resultado.energia_padre_kwh == 500.0
    repo.obtener_facturas_planta.assert_not_called()
