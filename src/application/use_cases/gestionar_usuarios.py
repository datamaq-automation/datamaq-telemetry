"""src/application/use_cases/gestionar_usuarios.py."""

import uuid

from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.domain.auth.value_objects import NombreUsuario


class GestionarUsuariosUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        hash_service: HashContrasenaService,
    ) -> None:
        self.repo_usuarios = repo_usuarios
        self.hash_service = hash_service

    def crear_usuario(
        self,
        usuario: str,
        contrasena: str,
        esta_activo: bool = True,
        rol: str = "operador",
        organizacion_id: str | None = None,
    ) -> UsuarioAuth:
        nombre = NombreUsuario(usuario).valor
        existente = self.repo_usuarios.obtener_por_usuario(nombre)
        if existente is not None:
            return existente

        entidad = UsuarioAuth(
            id=str(uuid.uuid4()),
            usuario=nombre,
            hash_contrasena=self.hash_service.generar_hash(contrasena),
            esta_activo=esta_activo,
            rol=rol,
            organizacion_id=organizacion_id,
        )
        return self.repo_usuarios.guardar(entidad)
