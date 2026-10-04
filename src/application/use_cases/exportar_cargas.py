"""src/application/use_cases/exportar_cargas.py."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from src.application.mappers.csv_streaming_mapper import CsvStreamingMapper
from src.domain.maquinas.ports import (
    RepositorioIntervalosActividadPort,
    RepositorioMáquinasPort,
)


class ExportarCargasUseCase:
    """Caso de uso para exportar intervalos de actividad NILM y atribución a CSV streaming."""

    def __init__(
        self,
        repo_cargas: RepositorioMáquinasPort,
        repo_intervalos: RepositorioIntervalosActividadPort,
    ):
        self.repo_cargas = repo_cargas
        self.repo_intervalos = repo_intervalos

    def ejecutar(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 30,
        solo_no_atribuidos: bool = False,
    ) -> Generator[str, None, None]:
        fin = hasta or datetime.now(timezone.utc)
        inicio = desde or (fin - timedelta(days=dias))

        cargas = self.repo_cargas.listar_por_dispositivo(dispositivo_id)
        mapa_cargas: dict[str, tuple[str, str]] = {
            c.id: (c.nombre, c.categoria.value if hasattr(c.categoria, "value") else str(c.categoria)) for c in cargas
        }

        intervalos = self.repo_intervalos.listar_por_dispositivo(dispositivo_id, inicio, fin)
        if solo_no_atribuidos:
            intervalos = [i for i in intervalos if not i.esta_atribuido]

        return CsvStreamingMapper.generar_csv_cargas(iter(intervalos), mapa_cargas=mapa_cargas)
