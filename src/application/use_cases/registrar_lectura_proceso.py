"""src/application/use_cases/registrar_lectura_proceso.py."""

from datetime import datetime

from src.domain.produccion.ports import RepositorioVariablesProcesoPort
from src.domain.produccion.value_objects import LecturaVariableProceso, TipoVariableProceso


class RegistrarLecturaProcesoUseCase:
    """Registra eventos e incrementos de variables de proceso industrial (sensores inductivos)."""

    def __init__(self, repo_proceso: RepositorioVariablesProcesoPort):
        self._repo_proceso = repo_proceso

    def ejecutar(
        self,
        maquina_id: str,
        momento: datetime,
        variable_tipo: TipoVariableProceso,
        delta_valor: float,
        valor_acumulado: float,
    ) -> LecturaVariableProceso:
        lectura = LecturaVariableProceso(
            momento=momento,
            variable_tipo=variable_tipo,
            delta_valor=delta_valor,
            valor_acumulado=valor_acumulado,
        )
        self._repo_proceso.guardar_lectura(lectura=lectura, maquina_id=maquina_id)
        return lectura
