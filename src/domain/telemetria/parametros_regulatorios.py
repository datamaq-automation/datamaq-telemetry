"""src/domain/telemetria/parametros_regulatorios.py.

Puerto de lectura de tarifas, facturas verificadas y parámetros regulatorios (Issue datamaq#111, fase 1).

El dominio no sabe si estos datos vienen de la base, de memoria o de otro lado: solo define qué puede
preguntar. Solo usa la stdlib (regla de `tests/test_architecture.py`).
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.telemetria.penalizacion_periodo import FacturaVerificada
    from src.domain.telemetria.tarifas_distribuidora import TarifaCapacidad


class RepositorioParametrosRegulatoriosPort(ABC):
    """Lectura de datos regulatorios y de negocio con vigencia y fuente. Sin escritura desde el dominio."""

    @abstractmethod
    def obtener_tarifa_capacidad(self, distribuidora: str, periodo: str) -> "TarifaCapacidad | None":
        """Precio de capacidad verificado para la distribuidora y el período, o None si no está cargado."""

    @abstractmethod
    def obtener_factura_verificada(self, planta_id: str, periodo: str) -> "FacturaVerificada | None":
        """Factura verificada contra el PDF para la planta y el período, o None si no está cargada."""

    @abstractmethod
    def factor_recargo_exceso(self, distribuidora: str, tarifa: str) -> Decimal:
        """Factor de recargo por exceso de potencia de la distribuidora y tarifa (1,5 en Edesur T3 MT)."""

    @abstractmethod
    def limite_tg_fi_regimen_1992(self, distribuidora: str, tarifa: str) -> Decimal:
        """Límite de tg phi del régimen de energía reactiva 1992 de la distribuidora y tarifa (0,62 en EDELAP T5M12)."""
