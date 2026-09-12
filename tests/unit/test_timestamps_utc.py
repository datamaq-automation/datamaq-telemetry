"""tests/unit/test_timestamps_utc.py — Garantías de que todo datetime sale de la API como UTC aware (ISO-8601 con `Z`).

Un datetime naive serializa como `2026-09-01T23:20:00`, sin offset, y JavaScript lo
interpreta como hora local: la API mentía por el valor del offset del cliente.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.dtos.telemetria_dto import LecturaInstantaneaDTO, MedicionFaseDTO
from src.application.dtos.tipos import _asegurar_utc
from src.infrastructure.sqlalchemy.models import Base, TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.types import UtcDateTime

BUENOS_AIRES = timezone(timedelta(hours=-3))


def _sesion() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_columna_devuelve_aware_utc_desde_la_bd() -> None:
    db = _sesion()
    db.add(
        TelemetryInstantaneousModel(
            id=1, device_id="dev-1", recorded_at=datetime(2026, 9, 1, 23, 20, tzinfo=timezone.utc)
        )
    )
    db.commit()
    db.expunge_all()

    leido = db.get(TelemetryInstantaneousModel, 1)

    assert leido is not None
    assert leido.recorded_at.tzinfo is not None
    assert leido.recorded_at.utcoffset() == timedelta(0)


def test_columna_convierte_a_utc_al_escribir_un_offset_local() -> None:
    """Sin conversión al escribir, el driver descarta el tzinfo y guarda el wall-clock local."""
    db = _sesion()
    local = datetime(2026, 9, 1, 20, 20, tzinfo=BUENOS_AIRES)
    db.add(TelemetryInstantaneousModel(id=1, device_id="dev-1", recorded_at=local))
    db.commit()
    db.expunge_all()

    leido = db.get(TelemetryInstantaneousModel, 1)

    assert leido is not None
    assert leido.recorded_at == local
    assert leido.recorded_at.hour == 23


def test_decorador_preserva_none_en_ambos_sentidos() -> None:
    tipo = UtcDateTime()

    assert tipo.process_bind_param(None, None) is None
    assert tipo.process_result_value(None, None) is None


def test_decorador_asume_utc_en_un_naive_entrante() -> None:
    tipo = UtcDateTime()
    naive = datetime(2026, 9, 1, 23, 20)

    assert tipo.process_bind_param(naive, None) == naive
    leido = tipo.process_result_value(naive, None)
    assert leido is not None and leido.tzinfo is timezone.utc


def test_dto_serializa_con_sufijo_z() -> None:
    dto = LecturaInstantaneaDTO(
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 1, 23, 20),  # naive, como venía de la BD
        fase_r=MedicionFaseDTO(),
        fase_s=MedicionFaseDTO(),
        fase_t=MedicionFaseDTO(),
    )

    assert '"registrado_en":"2026-09-01T23:20:00Z"' in dto.model_dump_json()


def test_dto_convierte_offset_local_a_utc() -> None:
    dto = LecturaInstantaneaDTO(
        dispositivo_id="dev-1",
        registrado_en=datetime(2026, 9, 1, 20, 20, tzinfo=BUENOS_AIRES),
        fase_r=MedicionFaseDTO(),
        fase_s=MedicionFaseDTO(),
        fase_t=MedicionFaseDTO(),
    )

    assert '"registrado_en":"2026-09-01T23:20:00Z"' in dto.model_dump_json()


def test_asegurar_utc_normaliza_naive_y_aware() -> None:
    assert _asegurar_utc(datetime(2026, 9, 1, 23, 20)).tzinfo is timezone.utc
    assert _asegurar_utc(datetime(2026, 9, 1, 20, 20, tzinfo=BUENOS_AIRES)).hour == 23
    ya_utc = datetime(2026, 9, 1, 23, 20, tzinfo=timezone.utc)
    assert _asegurar_utc(ya_utc) == ya_utc
