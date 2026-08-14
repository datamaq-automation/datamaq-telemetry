from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.models import Base


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )


@lru_cache(maxsize=1)
def get_session_factory():
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
