"""tests/unit/test_parametros_regulatorios.py — tarifas, facturas y parámetros regulatorios en SQL (datamaq#111).

Dos cosas que fija este archivo:
1. La carga inicial reproduce, valor por valor, los literales que vivían en el dominio antes de #111.
2. El adaptador SQL y el repositorio en memoria devuelven lo mismo para las mismas claves, y el SQL falla cerrado
   (LookupError) si falta un parámetro regulatorio.
"""

import dataclasses
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.adapters.gateways.in_memory_parametros_regulatorios import RepositorioParametrosRegulatoriosEnMemoria
from src.adapters.gateways.parametros_regulatorios_iniciales import (
    FACTURAS_VERIFICADAS_INICIALES,
    PARAMETROS_REGULATORIOS_INICIALES,
    TARIFAS_CAPACIDAD_INICIALES,
)
from src.domain.telemetria.penalizacion_periodo import MOTIVO_PERIODO_SIN_TARIFA, calcular_penalizacion_periodo
from src.domain.telemetria.tarifas_distribuidora import calcular_penalizacion_reactiva_edelap
from src.infrastructure.sqlalchemy.models_parametros_regulatorios import (
    FacturaVerificadaModel,
    ParametroRegulatorioModel,
    TarifaCapacidadModel,
)
from src.infrastructure.sqlalchemy.repositories.parametros_regulatorios_repository import (
    RepositorioParametrosRegulatoriosSqlAlchemy,
)

PLANTA_DURAX = "c64fd625-0037-4caa-b68a-800e8e0ee548"
PLANTA_UPP = "4f68f653-a604-4834-8154-31f938248572"


@pytest.fixture
def repo_memoria() -> RepositorioParametrosRegulatoriosEnMemoria:
    return RepositorioParametrosRegulatoriosEnMemoria()


@pytest.fixture
def sesion_sqlite():
    """Base SQLite en memoria con la carga inicial, cargada como lo hace la migración."""
    engine = create_engine("sqlite://")
    for modelo in (TarifaCapacidadModel, FacturaVerificadaModel, ParametroRegulatorioModel):
        modelo.__table__.create(engine)
    sesion = sessionmaker(bind=engine)()
    for t in TARIFAS_CAPACIDAD_INICIALES:
        sesion.add(
            TarifaCapacidadModel(
                distribuidora=t["distribuidora"],
                tarifa=t["tarifa"],
                periodo=t["periodo"],
                fuente_archivo=t["fuente_archivo"],
                fuente_metodo=t["fuente_metodo"],
                vigencia_desde=date.fromisoformat(t["vigencia_desde"]),
                importe_capacidad_convenida_ars=Decimal(t["importe_capacidad_convenida_ars"]),
                csc_kw=Decimal(t["csc_kw"]),
            )
        )
    for f in FACTURAS_VERIFICADAS_INICIALES:
        sesion.add(
            FacturaVerificadaModel(
                planta_id=f["planta_id"],
                distribuidora=f["distribuidora"],
                tarifa=f["tarifa"],
                periodo=f["periodo"],
                fuente_archivo=f["fuente_archivo"],
                fuente_metodo=f["fuente_metodo"],
                adquirida_kw=Decimal(f["adquirida_kw"]) if f["adquirida_kw"] else None,
                tg_fi_bloque_punta=Decimal(f["tg_fi_bloque_punta"]) if f["tg_fi_bloque_punta"] else None,
                tg_fi_bloque_valle=Decimal(f["tg_fi_bloque_valle"]) if f["tg_fi_bloque_valle"] else None,
                tg_fi_bloque_resto=Decimal(f["tg_fi_bloque_resto"]) if f["tg_fi_bloque_resto"] else None,
            )
        )
    for p in PARAMETROS_REGULATORIOS_INICIALES:
        sesion.add(
            ParametroRegulatorioModel(
                clave=p["clave"],
                valor=Decimal(p["valor"]),
                distribuidora=p["distribuidora"],
                tarifa=p["tarifa"],
                vigencia_desde=None,
                fuente_archivo=p["fuente_archivo"],
                fuente_metodo=p["fuente_metodo"],
            )
        )
    sesion.commit()
    return sesion


# --- 1. La carga inicial reproduce los literales de antes de #111 -------------------------------------------


def test_tarifa_edesur_t3_mt_2025_07_es_la_de_los_literales(repo_memoria):
    tarifa = repo_memoria.obtener_tarifa_capacidad("Edesur", "2025-07")

    assert tarifa is not None
    assert tarifa.tarifa == "T3 MT"
    assert tarifa.importe_capacidad_convenida_ars == Decimal("3521212.94")
    assert tarifa.csc_kw == Decimal("848.40")
    assert tarifa.fuente_archivo == "Cristal Avellaneda - EDESUR/2025-07.pdf"
    assert tarifa.vigencia_desde == "2025-07-01"


def test_factores_regulatorios_son_los_literales(repo_memoria):
    assert repo_memoria.factor_recargo_exceso("Edesur", "T3 MT") == Decimal("1.5")
    assert repo_memoria.limite_tg_fi_regimen_1992("EDELAP", "T5M12") == Decimal("0.62")


def test_factura_durax_2025_07_es_la_del_literal(repo_memoria):
    factura = repo_memoria.obtener_factura_verificada(PLANTA_DURAX, "2025-07")

    assert factura is not None
    assert factura.distribuidora == "Edesur"
    assert factura.tarifa == "T3 MT"
    assert factura.adquirida_kw == Decimal("930.00")
    assert factura.tg_fi_por_bloque is None


@pytest.mark.parametrize(
    ("periodo", "tg"),
    [
        ("2024-08", (Decimal("0.431"), Decimal("0.438"), Decimal("0.426"))),
        ("2023-12", (Decimal("0.483"), Decimal("0.492"), Decimal("0.481"))),
    ],
)
def test_facturas_upp_son_las_del_literal(repo_memoria, periodo, tg):
    factura = repo_memoria.obtener_factura_verificada(PLANTA_UPP, periodo)

    assert factura is not None
    assert factura.distribuidora == "EDELAP"
    assert factura.tarifa == "T5M12"
    assert factura.tg_fi_por_bloque == tg


def test_no_se_inventan_datos_fuera_de_la_carga_inicial(repo_memoria):
    assert repo_memoria.obtener_tarifa_capacidad("EDELAP", "2024-08") is None
    assert repo_memoria.obtener_tarifa_capacidad("Edesur", "2025-06") is None
    assert repo_memoria.obtener_factura_verificada(PLANTA_DURAX, "2025-06") is None
    assert repo_memoria.obtener_factura_verificada("planta-desconocida", "2025-07") is None


def test_cada_fila_de_la_carga_inicial_tiene_fuente(repo_memoria):
    for fila in (*TARIFAS_CAPACIDAD_INICIALES, *FACTURAS_VERIFICADAS_INICIALES, *PARAMETROS_REGULATORIOS_INICIALES):
        assert fila["fuente_archivo"], fila
        assert fila["fuente_metodo"], fila


# --- 2. El adaptador SQL y el repositorio en memoria coinciden ----------------------------------------------


def test_sql_devuelve_la_misma_tarifa_que_la_memoria(sesion_sqlite, repo_memoria):
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    assert sql.obtener_tarifa_capacidad("Edesur", "2025-07") == repo_memoria.obtener_tarifa_capacidad(
        "Edesur", "2025-07"
    )
    assert sql.obtener_tarifa_capacidad("EDELAP", "2024-08") is None


@pytest.mark.parametrize(
    ("planta", "periodo"),
    [(PLANTA_DURAX, "2025-07"), (PLANTA_UPP, "2024-08"), (PLANTA_UPP, "2023-12"), (PLANTA_DURAX, "2025-06")],
)
def test_sql_devuelve_la_misma_factura_que_la_memoria(sesion_sqlite, repo_memoria, planta, periodo):
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    assert sql.obtener_factura_verificada(planta, periodo) == repo_memoria.obtener_factura_verificada(planta, periodo)


def test_sql_devuelve_los_factores_regulatorios(sesion_sqlite):
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    assert sql.factor_recargo_exceso("Edesur", "T3 MT") == Decimal("1.5")
    assert sql.limite_tg_fi_regimen_1992("EDELAP", "T5M12") == Decimal("0.62")


def test_sql_falla_cerrado_si_falta_un_parametro(sesion_sqlite):
    sesion_sqlite.query(ParametroRegulatorioModel).filter(
        ParametroRegulatorioModel.clave == "factor_recargo_exceso"
    ).delete()
    sesion_sqlite.commit()
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    with pytest.raises(LookupError, match="factor_recargo_exceso"):
        sql.factor_recargo_exceso("Edesur", "T3 MT")


# --- 3. Versiones: una corrección es otra fila; gana la vigente más reciente --------------------------------


def test_correccion_de_tarifa_con_vigencia_mas_nueva_gana(sesion_sqlite):
    sesion_sqlite.add(
        TarifaCapacidadModel(
            distribuidora="Edesur",
            tarifa="T3 MT",
            periodo="2025-07",
            fuente_archivo="Cristal Avellaneda - EDESUR/2025-07.pdf",
            fuente_metodo="transcripcion_verificada",
            vigencia_desde=date(2025, 8, 1),
            importe_capacidad_convenida_ars=Decimal("3600000.00"),
            csc_kw=Decimal("848.40"),
        )
    )
    sesion_sqlite.commit()
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    tarifa = sql.obtener_tarifa_capacidad("Edesur", "2025-07")

    assert tarifa is not None
    assert tarifa.importe_capacidad_convenida_ars == Decimal("3600000.00")
    assert tarifa.vigencia_desde == "2025-08-01"


def test_correccion_de_factura_gana_la_fila_mas_nueva(sesion_sqlite):
    sesion_sqlite.add(
        FacturaVerificadaModel(
            planta_id=PLANTA_DURAX,
            distribuidora="Edesur",
            tarifa="T3 MT",
            periodo="2025-07",
            fuente_archivo="Cristal Avellaneda - EDESUR/2025-07-correccion.pdf",
            fuente_metodo="transcripcion_verificada",
            adquirida_kw=Decimal("940.00"),
        )
    )
    sesion_sqlite.commit()
    sql = RepositorioParametrosRegulatoriosSqlAlchemy(sesion_sqlite)

    factura = sql.obtener_factura_verificada(PLANTA_DURAX, "2025-07")

    assert factura is not None
    assert factura.adquirida_kw == Decimal("940.00")


# --- 4. Un parámetro faltante no es un 500: el período queda sin cifra y con su motivo ----------------------


class _RepoSinParametros(RepositorioParametrosRegulatoriosEnMemoria):
    def factor_recargo_exceso(self, distribuidora: str, tarifa: str) -> Decimal:
        raise LookupError("factor sin cargar")

    def limite_tg_fi_regimen_1992(self, distribuidora: str, tarifa: str) -> Decimal:
        raise LookupError("límite sin cargar")


def test_parametro_faltante_en_recargo_da_periodo_sin_cifra_con_motivo():
    penalizacion = calcular_penalizacion_periodo(_RepoSinParametros(), PLANTA_DURAX, "2025-07")

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_PERIODO_SIN_TARIFA
    assert penalizacion.distribuidora == "Edesur"


def test_parametro_faltante_en_limite_reactivo_da_periodo_sin_cifra_con_motivo():
    penalizacion = calcular_penalizacion_periodo(_RepoSinParametros(), PLANTA_UPP, "2024-08")

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_PERIODO_SIN_TARIFA


def test_tarifa_escrita_distinto_no_tira_500_y_queda_sin_cifra():
    """data/organizaciones.yml escribe 'T3-MT'; la carga inicial usa 'T3 MT'. Sin cifra, no error."""

    class _RepoTarifaDistinta(RepositorioParametrosRegulatoriosEnMemoria):
        def obtener_factura_verificada(self, planta_id, periodo):
            factura = super().obtener_factura_verificada(planta_id, periodo)
            return dataclasses.replace(factura, tarifa="T3-MT") if factura else None

    penalizacion = calcular_penalizacion_periodo(_RepoTarifaDistinta(), PLANTA_DURAX, "2025-07")

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_PERIODO_SIN_TARIFA


def test_el_texto_del_regimen_sigue_al_limite_recibido():
    reactiva = calcular_penalizacion_reactiva_edelap(
        periodo="2025-01",
        fuente_archivo="sintético",
        tg_fi_por_bloque=(Decimal("0.10"),),
        limite_tg_fi=Decimal("0.70"),
    )

    assert reactiva.regimen == "contrato nacional 1992 (tg phi <= 0,70)"
