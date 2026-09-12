"""src/application/use_cases/exportar_disponibilidad.py."""
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from src.application.mappers.csv_streaming_mapper import CsvStreamingMapper
from src.domain.disponibilidad.exceptions import MaquinaNoEncontradaError
from src.domain.disponibilidad.ports import (
    RepositorioEventosDisponibilidadPort,
    RepositorioMaquinasPort,
)
from src.domain.disponibilidad.services import CalculadorMetricasOEEService


class ExportarDisponibilidadUseCase:
    """Caso de uso para exportar eventos de disponibilidad y métricas OEE en streaming CSV."""

    def __init__(
        self,
        repo_maquinas: RepositorioMaquinasPort,
        repo_eventos: RepositorioEventosDisponibilidadPort,
    ):
        self.repo_maquinas = repo_maquinas
        self.repo_eventos = repo_eventos

    def ejecutar(
        self,
        maquina_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 30,
    ) -> Generator[str, None, None]:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")

        fin = hasta or datetime.now(timezone.utc)
        inicio = desde or (fin - timedelta(days=dias))

        eventos = self.repo_eventos.listar_por_rango(maquina_id, inicio, fin)
        metricas = CalculadorMetricasOEEService.calcular_metricas(eventos, inicio=inicio, fin=fin)

        mtbf_str = f"{metricas.mtbf_horas:.1f}h" if metricas.mtbf_horas is not None else "N/A"
        mttr_str = f"{metricas.mttr_horas:.1f}h" if metricas.mttr_horas is not None else "N/A"
        resumen_kpi = (
            f"Resumen OEE: {metricas.disponibilidad_oee_pct:.1f}% | "
            f"MTBF: {mtbf_str} | MTTR: {mttr_str} | "
            f"Paradas no prog: {metricas.cantidad_paradas_no_programadas} | "
            f"Periodo: {inicio.strftime('%Y-%m-%d')} a {fin.strftime('%Y-%m-%d')}"
        )

        return CsvStreamingMapper.generar_csv_disponibilidad(iter(eventos), resumen_kpi=resumen_kpi)
