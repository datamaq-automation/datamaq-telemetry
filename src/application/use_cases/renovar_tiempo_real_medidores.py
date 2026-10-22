"""src/application/use_cases/renovar_tiempo_real_medidores.py — Renueva `realtime_sync_mode` según quién mira en vivo.

Ver `src/domain/telemetria/servicios/alcance_tiempo_real.py` y tests/unit/test_renovar_tiempo_real_medidores.py.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domain.cargas.ports import ComandoRafagaPort
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import RepositorioDispositivosPort
from src.domain.telemetria.servicios.alcance_tiempo_real import AlcanceTiempoReal, publico_recientemente

SEGUNDOS_TIEMPO_REAL: int = 120


@dataclass(frozen=True)
class ResultadoRenovacionTiempoReal:
    renovados: int
    omitidos_sin_recepcion_reciente: int


class RenovarTiempoRealMedidoresUseCase:
    def __init__(self, repo_dispositivos: RepositorioDispositivosPort, comando_rafaga: ComandoRafagaPort) -> None:
        self._repo = repo_dispositivos
        self._comando = comando_rafaga

    def ejecutar(self, alcance: AlcanceTiempoReal, ahora: datetime) -> ResultadoRenovacionTiempoReal:
        renovados = 0
        omitidos = 0
        for dispositivo in self._dispositivos_del_alcance(alcance):
            if not (dispositivo.device_uid and dispositivo.device_uid.valor):
                continue
            if not publico_recientemente(dispositivo.visto_por_ultima_vez, ahora):
                omitidos += 1
                continue
            if self._comando.activar_rafaga(dispositivo.device_uid.valor, SEGUNDOS_TIEMPO_REAL):
                renovados += 1
        return ResultadoRenovacionTiempoReal(renovados=renovados, omitidos_sin_recepcion_reciente=omitidos)

    def _dispositivos_del_alcance(self, alcance: AlcanceTiempoReal) -> list[Dispositivo]:
        if alcance.todas:
            return self._repo.listar()
        por_id: dict[str, Dispositivo] = {}
        for organizacion_id in sorted(alcance.organizaciones):
            for dispositivo in self._repo.listar(organizacion_id=organizacion_id):
                por_id.setdefault(dispositivo.id, dispositivo)
        return list(por_id.values())
