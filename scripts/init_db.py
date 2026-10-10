import os
import sys

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from alembic.config import Config

from alembic import command
from src.infrastructure.settings.config import get_settings

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_alembic() -> Config:
    """Config de Alembic apuntando al alembic.ini del repo (la URL la resuelve env.py)."""
    return Config(os.path.join(RAIZ, "alembic.ini"))


def init_database():
    settings = get_settings()
    print(f"[*] Conectando a MySQL en {settings.DB_HOST}:{settings.DB_PORT}...")
    try:
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            charset="utf8mb4",
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        conn.commit()
        conn.close()
        print(f"[+] Base de datos `{settings.DB_NAME}` verificada/creada exitosamente.")

        print("[*] Aplicando migraciones de esquema (alembic upgrade head)...")
        print(
            "[i] Si la BD ya tenía tablas legacy, use: .venv/bin/alembic stamp 209ce0774d59 && .venv/bin/alembic upgrade head"
        )
        command.upgrade(_config_alembic(), "head")
        print("[+] Migraciones aplicadas correctamente.")

    except Exception as e:
        print(f"[!] Error inicializando la base de datos: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_database()
