from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.domain.auth.entities import UsuarioAuth


class RepositorioUsuariosPort(ABC):
    @abstractmethod
    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        pass

    @abstractmethod
    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        pass


class GeneradorTokenPort(ABC):
    @abstractmethod
    def generar(self, usuario_id: str, usuario: str, expira_en: datetime, rol: str = "operador") -> str:
        pass

    @abstractmethod
    def verificar(self, token: str) -> dict[str, Any] | None:
        pass
