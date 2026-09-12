"""src/domain/disponibilidad/servicios/clasificador_disponibilidad.py."""

from src.domain.disponibilidad.value_objects import EstadoMaquina


class ClasificadorDisponibilidadService:
    """Clasifica el estado instantáneo de una máquina comparando potencia contra un umbral calibrado."""

    @staticmethod
    def evaluar(potencia_w: float, umbral_marcha_w: float) -> EstadoMaquina:
        return EstadoMaquina.MARCHA if potencia_w >= umbral_marcha_w else EstadoMaquina.PARADA
