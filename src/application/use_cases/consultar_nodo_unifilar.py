"""src/application/use_cases/consultar_nodo_unifilar.py."""

from src.application.dtos.planta_estructura_dto import (
    PuntoPotenciaNodoUnifilarDTO,
    ResumenNodoUnifilarDTO,
)
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.agregacion_dispositivos import calcular_historico, calcular_resumen
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import NodoUnifilar, Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService


class ConsultarNodoUnifilarUseCase:
    """Telemetría agregada de un nodo del unifilar: suma de sus medidores frontera."""

    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_telemetria: RepositorioTelemetriaPort,
        consultar_telemetria: ConsultarTelemetriaUseCase,
    ):
        self.repo_organizaciones = repo_organizaciones
        self.repo_telemetria = repo_telemetria
        self.consultar_telemetria = consultar_telemetria

    def _resolver_planta(self, planta_id: str, organizacion_id: str | None) -> Planta:
        planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
        if planta is None or (organizacion_id is not None and planta.organizacion_id != organizacion_id):
            raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")
        return planta

    def _resolver_nodo(
        self, planta_id: str, nodo_id: str, organizacion_id: str | None
    ) -> tuple[NodoUnifilar, list[str]]:
        planta = self._resolver_planta(planta_id, organizacion_id)
        arbol = ArbolUnifilarService(self.repo_organizaciones.obtener_nodos_unifilar(planta.id))
        return arbol.obtener(nodo_id), arbol.medidores_frontera(nodo_id)

    def resumen(
        self,
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "day",
        zona: str = "America/Argentina/Buenos_Aires",
        dias: int | None = None,
    ) -> ResumenNodoUnifilarDTO:
        nodo, dispositivos_ids = self._resolver_nodo(planta_id, nodo_id, organizacion_id)

        potencia_sumada, energia_sumada = calcular_resumen(
            dispositivos_ids, self.repo_telemetria, self.consultar_telemetria, granularidad, zona, dias
        )

        return ResumenNodoUnifilarDTO(
            planta_id=planta_id,
            nodo_id=nodo.id,
            es_virtual=nodo.device_id is None,
            dispositivos_ids=dispositivos_ids,
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
        planta_id: str,
        nodo_id: str,
        organizacion_id: str | None = None,
        granularidad: str = "5m",
        horas: int = 24,
    ) -> list[PuntoPotenciaNodoUnifilarDTO]:
        _, dispositivos_ids = self._resolver_nodo(planta_id, nodo_id, organizacion_id)

        puntos = calcular_historico(dispositivos_ids, self.consultar_telemetria, granularidad, horas)
        return [
            PuntoPotenciaNodoUnifilarDTO(
                momento=p.momento,
                potencia_activa_total_w=p.potencia_activa_total_w,
                potencia_reactiva_total_var=p.potencia_reactiva_total_var,
                potencia_aparente_total_va=p.potencia_aparente_total_va,
                factor_desplazamiento_total=p.factor_desplazamiento_total,
                dispositivos_sin_dato=p.dispositivos_sin_dato,
            )
            for p in puntos
        ]
