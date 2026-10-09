#!/usr/bin/env python3
"""Auditoría de producción de solo lectura: imprime un JSON estable con los checks permitidos.

Uso:
  .venv/bin/python scripts/auditar_produccion.py [--host vps]

Sin SQL ni lógica aquí: el caso de uso decide qué checks corren y el adaptador ejecuta solo consultas
de su allowlist en sesión READ ONLY.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.application.use_cases.auditar_produccion import AuditarProduccionUseCase  # noqa: E402
from src.infrastructure.produccion.adaptador_ssh import (  # noqa: E402
    HOST_POR_DEFECTO,
    AdaptadorAuditoriaProduccionSsh,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoría de producción (solo lectura).")
    parser.add_argument("--host", default=HOST_POR_DEFECTO, help="Alias SSH del VPS (por defecto: vps)")
    args = parser.parse_args()
    adaptador = AdaptadorAuditoriaProduccionSsh(host=args.host)
    resultado = AuditarProduccionUseCase(adaptador).ejecutar()
    print(json.dumps(resultado, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
