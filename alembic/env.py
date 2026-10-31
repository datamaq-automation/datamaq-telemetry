import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.models import Base

# Import obligatorio aunque no se use por nombre: registra las tablas del contexto
# de cargas en `Base.metadata` para que autogenerate las vea.
from src.infrastructure.sqlalchemy import models_cargas  # noqa: F401  isort:skip

# Idem para el contexto del asistente conversacional.
from src.infrastructure.sqlalchemy import models_asistente  # noqa: F401  isort:skip

# Idem para el contexto de OAuth 2.0 PKCE.
from src.infrastructure.sqlalchemy import oauth_models  # noqa: F401  isort:skip

# Idem para el consumo MQTT por equipo y hora (#93).
from src.infrastructure.sqlalchemy import models_consumo_mqtt  # noqa: F401  isort:skip
from src.infrastructure.sqlalchemy import models_parametros_regulatorios  # noqa: F401  isort:skip

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    # disable_existing_loggers=False: en tests alembic corre dentro del mismo proceso que la app y, con el
    # default (True), deshabilita loggers ya creados (p. ej. "settings"). En producción corre como CLI aparte.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def resolver_database_url() -> str:
    """Resuelve la URL: override por DATABASE_URL (tests/autogenerate) o settings del proyecto."""
    return os.environ.get("DATABASE_URL") or get_settings().database_url


config.set_main_option("sqlalchemy.url", resolver_database_url())

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
