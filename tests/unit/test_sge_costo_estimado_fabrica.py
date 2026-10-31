"""tests/unit/test_sge_costo_estimado_fabrica.py — Fábrica del costo estimado sin sqlalchemy en el router (#95).

El router ya no recibe la Session: el repositorio de telemetría sale de su propia dependencia, que comparte
la Session de la request con el caso de uso de telemetría (FastAPI cachea get_db_session por request).
"""

from unittest.mock import MagicMock

from src.application.use_cases.consultar_costo_estimado import ConsultarCostoEstimadoUseCase
from src.infrastructure.fastapi.dependencies import get_repositorio_telemetria
from src.infrastructure.fastapi.routes.sge_router import get_consultar_costo_estimado_use_case
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLTelemetriaRepository


def test_fabrica_construye_el_caso_de_uso_con_las_tres_dependencias():
    repo_org = MagicMock()
    repo_telemetria = MagicMock()
    consultar_telemetria = MagicMock()

    uc = get_consultar_costo_estimado_use_case(
        repo_org=repo_org,
        repo_telemetria=repo_telemetria,
        consultar_telemetria=consultar_telemetria,
    )

    assert isinstance(uc, ConsultarCostoEstimadoUseCase)
    assert uc._repo_org is repo_org
    assert uc._repo_telemetria is repo_telemetria
    assert uc._consultar_telemetria is consultar_telemetria


def test_get_repositorio_telemetria_usa_la_sesion_recibida():
    sesion = MagicMock()

    repo = get_repositorio_telemetria(sesion)

    assert isinstance(repo, MySQLTelemetriaRepository)
    assert repo.db is sesion
