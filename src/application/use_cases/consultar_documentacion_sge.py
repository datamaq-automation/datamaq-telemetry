"""src/application/use_cases/consultar_documentacion_sge.py."""

from src.domain.sge.entities import ArticuloSge
from src.domain.sge.exceptions import RolNoAutorizadoParaPrevisualizacionError
from src.domain.sge.ports import RepositorioDocumentacionSgePort

ROLES_PREVIEW_PERMITIDOS: frozenset[str] = frozenset(
    {
        "superadmin",
        "admin",
        "auditor",
    }
)


class ConsultarDocumentacionSgeUseCase:
    """Caso de uso para consultar artículos y procedimientos operativos del SGE ISO 50001."""

    def __init__(self, repositorio: RepositorioDocumentacionSgePort):
        self._repo = repositorio

    def ejecutar(
        self,
        rol_usuario: str,
        rol_filtro: str | None = None,
    ) -> list[ArticuloSge]:
        """Consulta los artículos disponibles según el rol autenticado o filtro de previsualización."""
        rol_usuario_norm = rol_usuario.strip().lower() if rol_usuario else "operador"

        if rol_filtro is not None and rol_filtro.strip():
            filtro_norm = rol_filtro.strip().lower()
            if rol_usuario_norm not in ROLES_PREVIEW_PERMITIDOS and filtro_norm != rol_usuario_norm:
                raise RolNoAutorizadoParaPrevisualizacionError(
                    f"El rol '{rol_usuario}' no tiene privilegios para previsualizar documentación de otros roles."
                )
            return self._repo.listar_por_rol(filtro_norm)

        if rol_usuario_norm in ROLES_PREVIEW_PERMITIDOS:
            return self._repo.listar_todos()

        return self._repo.listar_por_rol(rol_usuario_norm)
