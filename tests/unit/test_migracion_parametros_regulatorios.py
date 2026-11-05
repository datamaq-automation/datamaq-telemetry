"""tests/unit/test_migracion_parametros_regulatorios.py — la migración e8a1f3c2b4d6 carga los valores de #111.

Los valores esperados están escritos a mano aquí, sin importar ningún módulo de src/: si alguien cambia los
datos iniciales del repositorio en memoria, este test no se mueve, y la migración (que congela sus datos) tampoco.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

RAIZ = Path(__file__).resolve().parents[2]
ALEMBIC_INI = RAIZ / "alembic.ini"
REVISION_ANTERIOR = "d5f2a9c1e7b3"
TABLAS = {"tarifa_capacidad", "factura_verificada", "parametro_regulatorio"}


@pytest.fixture
def base_migrada(tmp_path, monkeypatch):
    db = tmp_path / "migracion.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    return cfg, create_engine(f"sqlite:///{db}")


def test_tarifa_edesur_t3_mt_2025_07_carga_los_valores_escritos_a_mano(base_migrada):
    _, engine = base_migrada
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT distribuidora, tarifa, periodo, fuente_archivo, vigencia_desde, "
                "importe_capacidad_convenida_ars, csc_kw FROM tarifa_capacidad"
            )
        ).all()

    assert len(filas) == 1
    distribuidora, tarifa, periodo, fuente, vigencia, importe, csc = filas[0]
    assert (distribuidora, tarifa, periodo) == ("Edesur", "T3 MT", "2025-07")
    assert fuente == "Cristal Avellaneda - EDESUR/2025-07.pdf"
    assert str(vigencia) == "2025-07-01"
    assert float(importe) == pytest.approx(3521212.94)
    assert float(csc) == pytest.approx(848.40)


def test_facturas_verificadas_cargan_durax_y_upp_con_sus_valores(base_migrada):
    _, engine = base_migrada
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                "SELECT planta_id, periodo, adquirida_kw, tg_fi_bloque_punta, tg_fi_bloque_valle, tg_fi_bloque_resto "
                "FROM factura_verificada"
            )
        ).all()
    por_clave = {(f[0], f[1]): f for f in filas}

    durax = por_clave[("c64fd625-0037-4caa-b68a-800e8e0ee548", "2025-07")]
    assert float(durax[2]) == pytest.approx(930.00)
    assert durax[3] is None and durax[4] is None and durax[5] is None

    upp_2024 = por_clave[("4f68f653-a604-4834-8154-31f938248572", "2024-08")]
    assert [float(upp_2024[3]), float(upp_2024[4]), float(upp_2024[5])] == pytest.approx([0.431, 0.438, 0.426])

    upp_2023 = por_clave[("4f68f653-a604-4834-8154-31f938248572", "2023-12")]
    assert [float(upp_2023[3]), float(upp_2023[4]), float(upp_2023[5])] == pytest.approx([0.483, 0.492, 0.481])
    assert len(filas) == 3


def test_parametros_regulatorios_cargan_1_5_y_0_62_con_su_alcance_y_fuente(base_migrada):
    _, engine = base_migrada
    with engine.connect() as conn:
        filas = conn.execute(
            text("SELECT clave, valor, distribuidora, tarifa, fuente_archivo, fuente_metodo FROM parametro_regulatorio")
        ).all()
    por_clave = {f[0]: f for f in filas}

    factor = por_clave["factor_recargo_exceso"]
    assert float(factor[1]) == pytest.approx(1.5)
    assert (factor[2], factor[3]) == ("Edesur", "T3 MT")
    assert factor[5] == "transcripcion_verificada"

    limite = por_clave["limite_tg_fi_regimen_1992"]
    assert float(limite[1]) == pytest.approx(0.62)
    assert (limite[2], limite[3]) == ("EDELAP", "T5M12")
    assert limite[5] == (
        "Decisión registrada: contrato nacional de 1992 (decisions/2026-10-14_regimen-reactiva-edelap.md)"
    )
    assert len(filas) == 2


def test_downgrade_borra_las_tres_tablas(base_migrada):
    cfg, engine = base_migrada

    command.downgrade(cfg, REVISION_ANTERIOR)

    tablas = set(inspect(engine).get_table_names())
    assert not (TABLAS & tablas)
