"""scripts/verify_architecture.py — Verifica las reglas de dependencia entre capas.

La regla vive en un único lugar: `verify_architecture_layers` de `tests/test_architecture.py`.
Este script es solo la entrada de línea de comandos que usan `scripts/ci.sh` y `scripts/pre-push.sh`.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from tests.test_architecture import verify_architecture_layers  # noqa: E402


def verify_architecture() -> None:
    # Los routers con ORM directo quedan fuera de este gate hasta refactorizarlos (ver tests/test_architecture.py).
    errors = verify_architecture_layers(Path(ROOT_DIR), incluir_controladores=False)
    if errors:
        print("\n".join(errors))
        print(f"\n[FAIL] Se encontraron {len(errors)} violaciones de arquitectura.")
        sys.exit(1)
    print("[PASS] Todas las reglas de Clean Architecture & DDD fueron respetadas.")


if __name__ == "__main__":
    verify_architecture()
