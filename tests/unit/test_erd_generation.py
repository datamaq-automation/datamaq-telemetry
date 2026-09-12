"""tests/unit/test_erd_generation.py."""
import os
import subprocess
import sys

from scripts.generate_erd import generate_mermaid_erd
from src.infrastructure.sqlalchemy.models import Base

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_erd_generation_contains_all_models():
    mermaid = generate_mermaid_erd()

    # Verificar que todas las tablas de SQLAlchemy estén presentes
    for table_name in Base.metadata.tables.keys():
        assert table_name.upper() in mermaid, f"La tabla {table_name} debe estar en el diagrama Mermaid"


def test_erd_file_is_in_sync():
    # Ejecutar el check del script
    cmd = [sys.executable, os.path.join(ROOT_DIR, "scripts", "generate_erd.py"), "--check"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"docs/database_erd.md está desactualizado:\n{result.stderr}"
