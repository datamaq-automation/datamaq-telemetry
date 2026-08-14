import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from config import settings
from database import engine, Base
import models


def init_database():
    print(f"[*] Conectando a MySQL en {settings.DB_HOST}:{settings.DB_PORT}...")
    try:
        # Step 1: Ensure database exists
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            charset="utf8mb4",
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        conn.close()
        print(f"[+] Base de datos `{settings.DB_NAME}` verificada/creada exitosamente.")

        # Step 2: Create all tables via SQLAlchemy
        print("[*] Creando tablas del esquema de telemetría...")
        Base.metadata.create_all(bind=engine)
        print("[+] Todas las tablas creadas correctamente.")

    except Exception as e:
        print(f"[!] Error inicializando la base de datos: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_database()
