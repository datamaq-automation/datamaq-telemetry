"""tests/unit/test_cargar_tarifa.py — scripts/cargar_tarifa.py (datamaq#111). Solo base SQLite de prueba.

Garantías: sin `--aplicar` no se escribe nada; con `--aplicar` se inserta una fila que el adaptador ve como vigente;
los datos inválidos se rechazan antes de tocar la base.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.cargar_tarifa import main
from src.infrastructure.sqlalchemy.models_parametros_regulatorios import TarifaCapacidadModel
from src.infrastructure.sqlalchemy.repositories.parametros_regulatorios_repository import (
    RepositorioParametrosRegulatoriosSqlAlchemy,
)

ARGS_BASE = [
    "--distribuidora", "Edesur",
    "--tarifa", "T3 MT",
    "--periodo", "2025-08",
    "--importe-capacidad", "3600000.00",
    "--csc-kw", "848.40",
    "--vigencia-desde", "2025-08-01",
    "--fuente-archivo", "Cristal Avellaneda - EDESUR/2025-08.pdf",
    "--fuente-metodo", "transcripcion_verificada",
]  # fmt: skip


@pytest.fixture
def fabrica_sqlite():
    engine = create_engine("sqlite://")
    TarifaCapacidadModel.__table__.create(engine)
    return sessionmaker(bind=engine)


def _filas(fabrica) -> int:
    sesion = fabrica()
    try:
        return sesion.query(TarifaCapacidadModel).count()
    finally:
        sesion.close()


def test_simulacion_por_defecto_no_escribe_ni_usa_la_base(fabrica_sqlite):
    def fabrica_prohibida():
        raise AssertionError("la simulación no debe abrir sesión")

    assert main(ARGS_BASE, session_factory=fabrica_prohibida) == 0
    assert _filas(fabrica_sqlite) == 0


def test_aplicar_inserta_una_fila_que_el_adaptador_ve_como_vigente(fabrica_sqlite):
    assert main([*ARGS_BASE, "--aplicar"], session_factory=fabrica_sqlite) == 0

    tarifa = RepositorioParametrosRegulatoriosSqlAlchemy(fabrica_sqlite()).obtener_tarifa_capacidad("Edesur", "2025-08")

    assert tarifa is not None
    assert tarifa.importe_capacidad_convenida_ars == Decimal("3600000.00")
    assert tarifa.vigencia_desde == "2025-08-01"


@pytest.mark.parametrize(
    "reemplazo",
    [
        ("--importe-capacidad", "-1"),
        ("--importe-capacidad", "no-numero"),
        ("--csc-kw", "0"),
        ("--fuente-metodo", "  "),
    ],
)
def test_datos_invalidos_se_rechazan_sin_escribir(fabrica_sqlite, reemplazo):
    args = list(ARGS_BASE)
    clave, valor = reemplazo
    args[args.index(clave) + 1] = valor

    assert main([*args, "--aplicar"], session_factory=fabrica_sqlite) == 2
    assert _filas(fabrica_sqlite) == 0
