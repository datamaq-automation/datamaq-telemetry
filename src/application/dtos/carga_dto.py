"""src/application/dtos/carga_dto.py — Re-exporta DTOs de maquina_dto para compatibilidad.

Nota histórica: en la refactorización DDD Carga→Máquina, los DTOs fueron movidos a
maquina_dto.py pero algunos imports aún referenciaban este módulo. Se mantiene para
compatibilidad hacia atrás con use_cases y routers existentes.
"""

from src.application.dtos.maquina_dto import (
    AnalisisConsumoResponseDTO,
    AtribucionConsumoResponseDTO,
    CorregirIntervaloRequestDTO,
    EnsayoCreateDTO,
    EnsayoResponseDTO,
    EstadisticaCiclosDTO,
    FirmaManualRequestDTO,
    IntervaloActividadResponseDTO,
    ItemAtribucionDTO,
    MáquinaCreateDTO,
    MáquinaResponseDTO,
    MáquinaUpdateDTO,
    PerfilConsumoResponseDTO,
    PerfilLineaBaseDTO,
    ResumenPropuestaDTO,
)

__all__ = [
    "AnalisisConsumoResponseDTO",
    "AtribucionConsumoResponseDTO",
    "CorregirIntervaloRequestDTO",
    "EnsayoCreateDTO",
    "EnsayoResponseDTO",
    "EstadisticaCiclosDTO",
    "FirmaManualRequestDTO",
    "IntervaloActividadResponseDTO",
    "ItemAtribucionDTO",
    "MáquinaCreateDTO",
    "MáquinaResponseDTO",
    "MáquinaUpdateDTO",
    "PerfilConsumoResponseDTO",
    "PerfilLineaBaseDTO",
    "ResumenPropuestaDTO",
]
