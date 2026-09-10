"""Fachada de compatibilidad hacia atrás para los servicios de dominio de telemetría.

Los servicios han sido modularizados en submódulos especializados dentro del paquete
`src.domain.telemetria.servicios`:
- `calculos_potencia`: CalculadoraPotenciaService, AgregacionEnergiaService, FiltroDeduplicacionService
- `persistencia_alertas`: FiltroPersistenciaTemporalService
- `politicas_suscripcion`: PoliticaRetencionService, PoliticaSuscripcionService
- `analizador_calidad_metrologica`: AnalizadorMetrologicoService
- `evaluador_alertas_calidad`: EvaluadorAlertasCalidadService
"""

from src.domain.telemetria.servicios.aislamiento_broadcast import (
    debe_recibir_evento,
)
from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
    AnalizadorMetrologicoService,
)
from src.domain.telemetria.servicios.analizador_fasorial import (
    AnalizadorFasorialService,
    DiagnosticoFasorialRed,
    EvaluacionRotacionFase,
)
from src.domain.telemetria.servicios.calculos_potencia import (
    AgregacionEnergiaService,
    CalculadoraPotenciaService,
    FiltroDeduplicacionService,
)
from src.domain.telemetria.servicios.cooldown_notificaciones import (
    CooldownNotificacionesAlertasService,
)
from src.domain.telemetria.servicios.evaluador_alertas_calidad import (
    EvaluadorAlertasCalidadService,
)
from src.domain.telemetria.servicios.evaluador_anomalias_fases import (
    EvaluadorAnomaliasFasesService,
)
from src.domain.telemetria.servicios.persistencia_alertas import (
    FiltroPersistenciaTemporalService,
)
from src.domain.telemetria.servicios.politicas_suscripcion import (
    PoliticaRetencionService,
    PoliticaSuscripcionService,
)


class AnalizadorCalidadEnergiaService(
    AnalizadorMetrologicoService,
    EvaluadorAlertasCalidadService,
    EvaluadorAnomaliasFasesService,
):
    """Servicio compuesto de analítica metrológica y evaluación de alertas normativas."""

    pass


__all__ = [
    "AgregacionEnergiaService",
    "AnalizadorCalidadEnergiaService",
    "AnalizadorFasorialService",
    "AnalizadorMetrologicoService",
    "CalculadoraPotenciaService",
    "CooldownNotificacionesAlertasService",
    "DiagnosticoFasorialRed",
    "EvaluacionRotacionFase",
    "EvaluadorAlertasCalidadService",
    "EvaluadorAnomaliasFasesService",
    "FiltroDeduplicacionService",
    "FiltroPersistenciaTemporalService",
    "PoliticaRetencionService",
    "PoliticaSuscripcionService",
    "debe_recibir_evento",
]
