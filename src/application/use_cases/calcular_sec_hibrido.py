"""src/application/use_cases/calcular_sec_hibrido.py."""

from datetime import datetime

from src.domain.produccion.entities import (
    ConfiguracionMedicionMaquina,
    ResultadoSecHibrido,
)
from src.domain.produccion.ports import RepositorioVariablesProcesoPort
from src.domain.produccion.servicios.calculador_enpi_hibrido import (
    CalculadorEnpiHibridoService,
)


class CalcularSecHibridoUseCase:
    """Caso de uso para orquestar el cálculo de Consumo Específico según topología de medición."""

    def __init__(self, repo_proceso: RepositorioVariablesProcesoPort) -> None:
        self._repo_proceso = repo_proceso

    def ejecutar(
        self,
        maquina_id: str,
        periodo_inicio: datetime,
        periodo_fin: datetime,
        energia_kwh: float,
        unidades_produccion: float,
        horas_activas_proceso: float,
        potencia_media_kw: float | None = None,
        config_fallback: ConfiguracionMedicionMaquina | None = None,
    ) -> ResultadoSecHibrido:
        config = self._repo_proceso.obtener_configuracion(maquina_id)
        if config is None:
            if config_fallback is not None:
                config = config_fallback
            else:
                config = ConfiguracionMedicionMaquina(
                    maquina_id=maquina_id,
                    nombre=f"Máquina {maquina_id}",
                    potencia_nominal_kw=15.0,
                    nodo_alimentacion="TGBT-GENERAL",
                    dispositivo_medidor_id=None,
                )

        return CalculadorEnpiHibridoService.calcular(
            config=config,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            energia_kwh=energia_kwh,
            unidades_produccion=unidades_produccion,
            horas_activas_proceso=horas_activas_proceso,
            potencia_media_kw=potencia_media_kw,
        )
