"""src/application/use_cases/listar_usuarios.py — Listado global de cuentas, solo lectura (issue #102)."""

from src.application.dtos.usuario_listado_dto import UsuarioListadoDTO
from src.domain.auth.ports import RepositorioUsuariosPort


class ListarUsuariosUseCase:
    def __init__(self, repo_usuarios: RepositorioUsuariosPort) -> None:
        self.repo_usuarios = repo_usuarios

    def ejecutar(self) -> list[UsuarioListadoDTO]:
        # Literal de la decisión 2026-10-30: todas las cuentas. Superadmin visible: supuesto abierto (spec §6).
        return [UsuarioListadoDTO.model_validate(u, from_attributes=True) for u in self.repo_usuarios.listar_todos()]
