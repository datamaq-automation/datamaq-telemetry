from src.domain.auth.ports import RepositorioDispositivosConfiablesPort


class RevocarDispositivosConfiablesUseCase:
    def __init__(self, repo_dispositivos: RepositorioDispositivosConfiablesPort) -> None:
        self._repo = repo_dispositivos

    def ejecutar(self, usuario_id: str) -> int:
        return self._repo.revocar_todos_de_usuario(usuario_id)
