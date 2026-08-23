from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.models import Base

logger = get_logger("database")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        echo=False,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def create_tables_if_needed():
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[Warning] Could not auto-create tables on start: {e}")


def verificar_estado_migraciones(engine: Engine | None = None) -> dict[str, Any]:
    """Verifica si la base de datos está sincronizada con la revisión HEAD de Alembic.

    Registra una advertencia estructurada si se detecta un desfasaje entre el esquema
    de la base de datos y las migraciones definidas en el repositorio.
    """
    try:
        engine = engine or get_engine()
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

            raiz = Path(__file__).resolve().parents[3]
            alembic_ini = raiz / "alembic.ini"
            if not alembic_ini.exists():
                logger.info("alembic_ini_no_encontrado", path=str(alembic_ini))
                return {
                    "sincronizado": True,
                    "current_rev": current_rev,
                    "head_rev": None,
                    "detalle": "alembic_ini_no_encontrado",
                }

            config = Config(str(alembic_ini))
            script = ScriptDirectory.from_config(config)
            head_rev = script.get_current_head()

            sincronizado = current_rev == head_rev
            if not sincronizado:
                logger.warning(
                    "desfasaje_migraciones_detectado",
                    current_revision=current_rev,
                    head_revision=head_rev,
                    mensaje=f"DESFASAJE DE MIGRACIÓN DETECTADO: BD en '{current_rev}', Head esperado en '{head_rev}'. Ejecute 'alembic upgrade head'.",
                )
            else:
                logger.info(
                    "migraciones_verificadas",
                    current_revision=current_rev,
                    head_revision=head_rev,
                )
            return {
                "sincronizado": sincronizado,
                "current_rev": current_rev,
                "head_rev": head_rev,
            }
    except Exception as e:
        logger.warning("error_verificacion_migraciones", error=str(e))
        return {
            "sincronizado": False,
            "current_rev": None,
            "head_rev": None,
            "error": str(e),
        }


def verificar_conexion_db(engine: Engine | None = None) -> bool:
    """Verifica si es posible establecer conexión y ejecutar una consulta simple contra la BD."""
    try:
        from sqlalchemy import text

        engine = engine or get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
