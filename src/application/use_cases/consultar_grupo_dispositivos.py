"""src/application/use_cases/consultar_grupo_dispositivos.py."""

from src.application.dtos.grupo_dispositivos_dto import (
    PuntoPotenciaGrupoDTO,
    ResumenGrupoDispositivosDTO,
)
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.agregacion_dispositivos import calcular_historico, calcular_resumen
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.exceptions import GrupoDispositivosNoEncontradoError
from src.domain.telemetria.ports import RepositorioGruposDispositivosPort, RepositorioTelemetriaPort


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

        potencia_sumada, energia_sumada = calcular_resumen(
            grupo.dispositivos_ids, self.repo_telemetria, self.consultar_telemetria, granularidad, zona, dias
        )

        return ResumenGrupoDispositivosDTO(
            grupo_id=grupo_id,
            potencia_activa_total_w=potencia_sumada.potencia_activa_total_w,
            potencia_reactiva_total_var=potencia_sumada.potencia_reactiva_total_var,
            potencia_aparente_total_va=potencia_sumada.potencia_aparente_total_va,
            factor_desplazamiento_total=potencia_sumada.factor_desplazamiento_total,
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

        puntos = calcular_historico(grupo.dispositivos_ids, self.consultar_telemetria, granularidad, horas)
        return [
            PuntoPotenciaGrupoDTO(
                momento=p.momento,
                potencia_activa_total_w=p.potencia_activa_total_w,
                potencia_reactiva_total_var=p.potencia_reactiva_total_var,
                potencia_aparente_total_va=p.potencia_aparente_total_va,
                factor_desplazamiento_total=p.factor_desplazamiento_total,
                dispositivos_sin_dato=p.dispositivos_sin_dato,
            )
            for p in puntos
        ]
