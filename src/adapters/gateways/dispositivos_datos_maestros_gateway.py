"""src/adapters/gateways/dispositivos_datos_maestros_gateway.py."""

from datetime import datetime

from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioOrganizacionesPort
from src.domain.telemetria.servicios.datos_maestros_medidor import DatosMaestrosMedidorService
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class DispositivosConDatosMaestrosGateway(RepositorioDispositivosPort):
    """Decora el repositorio de dispositivos aplicando la precedencia del YAML en cada lectura.

    Instalación (`plantas[].medidores[]`) y contrato (acometida del unifilar) declarados
    en `data/organizaciones.yml` pisan lo que dice MySQL; lo no declarado sale de la base.
    Único punto de resolución: API, ingesta MQTT y verificación de propiedad ven lo mismo.
    Las escrituras pasan directo — la guarda contra editar campos gobernados vive en el caso de uso.
    """

    def __init__(self, base: RepositorioDispositivosPort, organizaciones: RepositorioOrganizacionesPort):
        self._base = base
        self._org = organizaciones

    def _resolver(self, dispositivo: Dispositivo | None) -> Dispositivo | None:
        if dispositivo is None:
            return None
        resuelto = DatosMaestrosMedidorService.aplicar_instalacion(
            dispositivo, self._org.obtener_instalacion_medidor(dispositivo.id)
        )
        if resuelto.planta_id:
            resuelto = DatosMaestrosMedidorService.aplicar_contrato(
                resuelto, self._org.obtener_nodos_unifilar(resuelto.planta_id)
            )
        return resuelto

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self._resolver(self._base.obtener_por_id(dispositivo_id))

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        return self._resolver(self._base.obtener_por_uid(uid))

    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        return [d for d in (self._resolver(x) for x in self._base.listar(planta_id, organizacion_id)) if d]

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return self._base.contar_por_organizacion(organizacion_id)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        return self._resolver(self._base.guardar(dispositivo)) or dispositivo

    def actualizar_heartbeat(
        self,
        dispositivo_id: str,
        estado: EstadoDispositivo,
        visto_por_ultima_vez: datetime,
        numero_serie: str | None = None,
        version_fw: str | None = None,
        version_hw: str | None = None,
    ) -> None:
        self._base.actualizar_heartbeat(
            dispositivo_id,
            estado,
            visto_por_ultima_vez,
            numero_serie=numero_serie,
            version_fw=version_fw,
            version_hw=version_hw,
        )
