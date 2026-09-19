"""src/domain/sge/entities.py."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CategoriaSge = Literal[
    "politica",
    "operacion",
    "mantenimiento",
    "normativa_enre",
    "metas_enpi",
]

CATEGORIAS_SGE_VALIDAS: frozenset[str] = frozenset(
    {
        "politica",
        "operacion",
        "mantenimiento",
        "normativa_enre",
        "metas_enpi",
    }
)


@dataclass(frozen=True)
class ArticuloSge:
    """Entidad inmutable que representa un artículo o procedimiento del SGE ISO 50001."""

    id: str
    titulo: str
    categoria: CategoriaSge
    roles_permitidos: tuple[str, ...]
    resumen: str
    puntos_clave: tuple[str, ...]
    acciones_inmediatas: tuple[str, ...]
    referencia_iso: str
    documento_url: str | None = None

    def es_visible_para(self, rol: str) -> bool:
        """Determina si el artículo es visible para el rol dado (case-insensitive)."""
        rol_normalizado = rol.strip().lower()
        return rol_normalizado in (r.lower() for r in self.roles_permitidos)


@dataclass(frozen=True)
class RegistroCapacitacionSge:
    """Evidencia inmutable de competencia y toma de conciencia (ISO 50001 §7.2 / §7.3)."""

    id: str
    usuario_id: str
    articulo_id: str
    rol_usuario: str
    fecha_completado: datetime
    version_doc: str
    comentarios: str | None = None
