"""tests/integration/test_consultas_por_request_unifilar.py — Consultas por request de resumen e histórico del unifilar (#14).

Fija cuántas consultas SQL y cuántos parseos de data/ hace cada request para una acometida MT con 2 medidores
frontera (el caso de Durax). Antes del fix: resumen 26 consultas + 42 parseos; histórico con referencia 17 + 36.
Si una de estas cifras sube, alguien volvió a resolver lo mismo por cada medidor: revisar antes de actualizar.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.fastapi.dependencies import get_consultar_nodo_unifilar_use_case
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.models import Base, DeviceModel, TelemetryInstantaneousModel
from src.infrastructure.yaml import loaders
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

CONSULTAS_RESUMEN = 12
CONSULTAS_HISTORICO_CON_REFERENCIA = 6

PLANTA = "planta-1"
ACOMETIDA = "nodo-acometida"
DISPOSITIVOS = ("dev-a", "dev-b")

ORGANIZACIONES_YML = f"""organizaciones:
  - id: org-1
    nombre: Org
    plantas:
      - id: {PLANTA}
        nombre: Planta
        nodos_unifilar:
          - {{id: {ACOMETIDA}, nombre: Acometida, tipo: ACOMETIDA, tension_nominal_v: 13200}}
          - {{id: tgbt-a, nombre: TGBT A, tipo: TABLERO, tension_nominal_v: 380, padre_id: {ACOMETIDA}, dispositivo_id: dev-a}}
          - {{id: tgbt-b, nombre: TGBT B, tipo: TABLERO, tension_nominal_v: 380, padre_id: {ACOMETIDA}, dispositivo_id: dev-b}}
"""


@pytest.fixture
def entorno(tmp_path: Path) -> Iterator[tuple[sessionmaker[Session], list[str], dict[str, int]]]:
    (tmp_path / "organizaciones.yml").write_text(ORGANIZACIONES_YML, encoding="utf-8")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _funciones_mysql(dbapi_connection, _registro):
        # CONVERT_TZ y DATE_FORMAT de MySQL no existen en SQLite; alcanza con que la consulta corra.
        dbapi_connection.create_function("convert_tz", 3, lambda ts, _origen, _destino: ts)
        dbapi_connection.create_function("date_format", 2, lambda ts, _formato: ts)

    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    with fabrica() as db:
        ahora = datetime.now(timezone.utc)
        for i, dev in enumerate(DISPOSITIVOS):
            db.add(DeviceModel(id=dev, device_uid=f"AABBCCDDEE0{i}", name=dev, facility_id=PLANTA))
        db.flush()
        for k in range(12):
            for j, dev in enumerate(DISPOSITIVOS):
                db.add(
                    TelemetryInstantaneousModel(
                        id=k * len(DISPOSITIVOS) + j + 1,
                        device_id=dev,
                        recorded_at=ahora - timedelta(minutes=5 * k),
                        total_active_power=300000,
                        total_reactive_power=90000,
                    )
                )
        db.commit()

    consultas: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _contar(_conn, _cursor, sentencia, _params, _contexto, _many):
        consultas.append(sentencia)

    parseos = {"n": 0}
    parsear = loaders._parsear_organizaciones_completas

    def _parseo_contado(data_dir: str) -> list[dict]:
        parseos["n"] += 1
        return parsear(data_dir)

    loaders.limpiar_cache_yaml()
    with (
        patch(
            "src.infrastructure.fastapi.dependencies.YamlOrganizacionesRepository",
            lambda: YamlOrganizacionesRepository(str(tmp_path)),
        ),
        patch.object(loaders, "_parsear_organizaciones_completas", _parseo_contado),
    ):
        yield fabrica, consultas, parseos
    loaders.limpiar_cache_yaml()


def _con_use_case(fabrica: sessionmaker[Session], fn) -> None:
    with fabrica() as db:
        fn(get_consultar_nodo_unifilar_use_case(db, get_settings()))


def test_resumen_de_acometida_con_dos_medidores(entorno):
    fabrica, consultas, parseos = entorno
    _con_use_case(fabrica, lambda uc: uc.resumen(PLANTA, ACOMETIDA, None))
    assert len(consultas) == CONSULTAS_RESUMEN
    assert parseos["n"] == 1  # Cache fría: un parseo para todo el request.

    consultas.clear()
    _con_use_case(fabrica, lambda uc: uc.resumen(PLANTA, ACOMETIDA, None))
    assert len(consultas) == CONSULTAS_RESUMEN
    assert parseos["n"] == 1  # Cache caliente: ninguno más.


def test_historico_con_potencia_referencia(entorno):
    fabrica, consultas, parseos = entorno

    def _historico(uc) -> None:
        uc.historico(PLANTA, ACOMETIDA, None, "5m", 24, None)
        uc.potencia_referencia(PLANTA, ACOMETIDA, None)

    _con_use_case(fabrica, _historico)
    assert len(consultas) == CONSULTAS_HISTORICO_CON_REFERENCIA
    assert parseos["n"] == 1


def test_el_dispositivo_y_la_suscripcion_se_resuelven_una_vez_por_request(entorno):
    fabrica, consultas, _ = entorno
    _con_use_case(fabrica, lambda uc: uc.resumen(PLANTA, ACOMETIDA, None))
    a_devices = [c for c in consultas if "FROM devices" in c]
    a_organizations = [c for c in consultas if "FROM organizations" in c]
    assert len(a_devices) == len(DISPOSITIVOS)
    assert len(a_organizations) == 1
