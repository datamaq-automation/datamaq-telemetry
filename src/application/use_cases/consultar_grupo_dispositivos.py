from src.application.dtos.grupo_dispositivos_dto import ResumenGrupoDispositivosDTO
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import EnergiaAgregada
from src.domain.telemetria.exceptions import GrupoDispositivosNoEncontradoError
from src.domain.telemetria.ports import RepositorioGruposDispositivosPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.agregador_grupo_dispositivos import AgregadorGrupoDispositivosService


class ConsultarGrupoDispositivosUseCase:
    def __init__(
        self,
        repo_grupos: RepositorioGruposDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        consultar_telemetria: ConsultarTelemetriaUseCase,
    ):
        self.repo_grupos = repo_grupos
        self.repo_telemetria = repo_telemetria
        self.consultar_telemetria = consultar_telemetria

    def resumen(
        self,
        grupo_id: str,
        granularidad: str = "day",
        zona: str = "America/Argentina/Buenos_Aires",
        dias: int | None = None,
    ) -> ResumenGrupoDispositivosDTO:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)

        lecturas_por_dispositivo = {
            dispositivo_id: self.repo_telemetria.obtener_ultima_instantanea(dispositivo_id)
            for dispositivo_id in grupo.dispositivos_ids
        }
        potencia_sumada = AgregadorGrupoDispositivosService.sumar_ultimas_lecturas(lecturas_por_dispositivo)

        agregados_por_dispositivo: dict[str, list[EnergiaAgregada]] = {}
        for dispositivo_id in grupo.dispositivos_ids:
            agregados_dto = self.consultar_telemetria.listar_energia_agregada(dispositivo_id, granularidad, zona, dias)
            agregados_por_dispositivo[dispositivo_id] = [
                EnergiaAgregada(periodo=a.periodo, energia_activa_neta_kwh=a.energia_activa_neta_kwh)
                for a in agregados_dto
            ]
        energia_sumada = AgregadorGrupoDispositivosService.sumar_energia_agregada(agregados_por_dispositivo)

        return ResumenGrupoDispositivosDTO(
            grupo_id=grupo_id,
            potencia_activa_total_w=potencia_sumada.potencia_activa_total_w,
            dispositivos_sin_dato=potencia_sumada.dispositivos_sin_dato,
            energia_agregada=[
                EnergiaAgregadaDTO(periodo=e.periodo, energia_activa_neta_kwh=e.energia_activa_neta_kwh)
                for e in energia_sumada
            ],
        )
