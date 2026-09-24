"""src/application/use_cases/gestionar_acceso_plantas.py."""

from src.application.dtos.auth_dto import AsignarPlantasRequestDTO, PlantaAccesoDTO
from src.domain.auth.entities import AccesoPlantaUsuario, UsuarioAuth
from src.domain.auth.exceptions import UsuarioNoEncontradoError
from src.domain.auth.ports import RepositorioAccesosPlantaPort, RepositorioUsuariosPort
from src.domain.auth.services import PoliticaAccesoPlantasService
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class GestionarAccesoPlantasUseCase:
    """Resuelve y administra las plantas visibles por usuario (R-02 del frontend).

    Las plantas son SSOT del YAML (`RepositorioOrganizacionesPort`); la tabla
    `user_facility_access` solo guarda la asignación explícita usuario ↔ planta.
    """

    def __init__(
        self,
        repo_accesos: RepositorioAccesosPlantaPort,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_usuarios: RepositorioUsuariosPort | None = None,
    ):
        self.repo_accesos = repo_accesos
        self.repo_organizaciones = repo_organizaciones
        self.repo_usuarios = repo_usuarios

    def resolver(self, usuario_id: str | None, rol: str, organizacion_id: str | None) -> list[PlantaAccesoDTO]:
        """Plantas accesibles para los claims dados. Lista vacía si no hay contexto de organización."""
        accesos = self.repo_accesos.listar_por_usuario(usuario_id) if usuario_id else []
        plantas = self.repo_organizaciones.listar_plantas(None)
        resueltas = PoliticaAccesoPlantasService.resolver(rol, organizacion_id, plantas, accesos)
        return [
            PlantaAccesoDTO(id=p.id, nombre=p.nombre, organizacion_id=p.organizacion_id, puede_cambiar=puede)
            for p, puede in resueltas
        ]

    @staticmethod
    def planta_activa(plantas: list[PlantaAccesoDTO]) -> str | None:
        return plantas[0].id if plantas else None

    def resolver_planta_permitida(
        self, usuario_id: str | None, rol: str, organizacion_id: str | None, planta_id: str | None
    ) -> str | None:
        """Planta efectiva de una consulta: la pedida si está permitida, o la activa si no se pidió.

        Una planta ajena, no asignada o inexistente lanza el mismo error, para no revelar
        a un usuario ajeno que el id existe.
        """
        permitidas = self.resolver(usuario_id, rol, organizacion_id)
        if planta_id is None:
            return self.planta_activa(permitidas)
        if any(p.id == planta_id for p in permitidas):
            return planta_id
        raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")

    def listar_asignadas(self, usuario_id: str) -> list[PlantaAccesoDTO]:
        usuario = self._obtener_usuario(usuario_id)
        return self.resolver(usuario.id, usuario.rol, usuario.organizacion_id)

    def asignar(self, usuario_id: str, dto: AsignarPlantasRequestDTO) -> list[PlantaAccesoDTO]:
        """Reemplaza las plantas asignadas; cada planta debe pertenecer a la organización del usuario."""
        usuario = self._obtener_usuario(usuario_id)
        accesos: list[AccesoPlantaUsuario] = []
        vistas: set[str] = set()
        for item in dto.plantas:
            if item.planta_id in vistas:
                continue
            planta = self.repo_organizaciones.obtener_planta_por_id(item.planta_id)
            if planta is None or planta.organizacion_id != usuario.organizacion_id:
                raise PlantaNoEncontradaError(
                    f"Planta con id '{item.planta_id}' no encontrada en la organización del usuario."
                )
            vistas.add(item.planta_id)
            accesos.append(
                AccesoPlantaUsuario(usuario_id=usuario.id, planta_id=planta.id, puede_cambiar=item.puede_cambiar)
            )
        self.repo_accesos.reemplazar(usuario.id, accesos)
        return self.resolver(usuario.id, usuario.rol, usuario.organizacion_id)

    def _obtener_usuario(self, usuario_id: str) -> UsuarioAuth:
        usuario = self.repo_usuarios.obtener_por_id(usuario_id) if self.repo_usuarios else None
        if usuario is None:
            raise UsuarioNoEncontradoError(f"Usuario con id '{usuario_id}' no encontrado.", usuario=usuario_id)
        return usuario
