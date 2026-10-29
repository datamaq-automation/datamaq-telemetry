"""src/infrastructure/paho_mqtt/ingesta_sin_escritura.py — Corte de persistencia para la réplica de solo lectura.

Con `INGESTA_PERSISTENCIA_HABILITADA=false` (api-dev), la ingesta sigue recibiendo y publicando en vivo, pero
ningún método que escribe llega a la base. Envolver el repositorio en vez de tocar cada caso de uso deja un único
punto de corte (decisión 2026-10-29, spec `specs/develop-replica-y-flujo-en-vivo.md` 3.2).
"""

from typing import Any

PREFIJOS_ESCRITURA = ("guardar", "actualizar", "eliminar", "capturar", "registrar")


class RepositorioSinEscritura:
    """Envuelve un repositorio: los métodos que escriben devuelven su primer argumento (o None) sin llamar al
    repositorio real; los de lectura pasan tal cual."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    def __getattr__(self, nombre: str) -> Any:
        attr = getattr(self._repo, nombre)
        if callable(attr) and nombre.startswith(PREFIJOS_ESCRITURA):
            return _no_escribe
        return attr


def _no_escribe(*args: Any, **kwargs: Any) -> Any:
    return args[0] if args else None


def sin_escritura_si(activo: bool, repo: Any) -> Any:
    return RepositorioSinEscritura(repo) if activo else repo
