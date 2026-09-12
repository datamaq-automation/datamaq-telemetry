"""src/application/use_cases/consultar_grupo_dispositivos.py."""
from src.application.dtos.grupo_dispositivos_dto import (
    PuntoPotenciaGrupoDTO,
    ResumenGrupoDispositivosDTO,
)
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

    def historico(
        self,
        grupo_id: str,
        granularidad: str = "5m",
        horas: int = 24,
    ) -> list[PuntoPotenciaGrupoDTO]:
        grupo = self.repo_grupos.obtener_por_id(grupo_id)
        if grupo is None:
            raise GrupoDispositivosNoEncontradoError(grupo_id)

        intervalo_segundos = ConsultarTelemetriaUseCase._resolver_intervalo_segundos(granularidad, horas)
        if intervalo_segundos <= 0:
            intervalo_segundos = 300

        lecturas_por_dispositivo: dict[str, list[tuple]] = {}
        for dispositivo_id in grupo.dispositivos_ids:
            lecturas_dto = self.consultar_telemetria.listar_instantaneas(
                dispositivo_id, limite=2000, granularidad=granularidad, horas=horas
            )
            lecturas_por_dispositivo[dispositivo_id] = [
                (lectura.registrado_en, lectura.potencia_activa_total_W) for lectura in lecturas_dto
            ]

        puntos = AgregadorGrupoDispositivosService.sumar_potencia_en_el_tiempo(
            lecturas_por_dispositivo, intervalo_segundos
        )
        return [
            PuntoPotenciaGrupoDTO(
                momento=p.momento,
                potencia_activa_total_w=p.potencia_activa_total_w,
                dispositivos_sin_dato=p.dispositivos_sin_dato,
            )
            for p in puntos
        ]
