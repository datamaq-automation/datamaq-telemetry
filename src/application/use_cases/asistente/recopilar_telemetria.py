"""src/application/use_cases/asistente/recopilar_telemetria.py."""

import logging
from typing import TYPE_CHECKING, Any

from src.domain.asistente.value_objects import IntencionUsuario

if TYPE_CHECKING:
    from src.application.dtos.telemetria_dto import TelemetriaLatestResponseDTO
    from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
    from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase

logger = logging.getLogger(__name__)


def _construir_resumen_telemetria(lectura: "TelemetriaLatestResponseDTO") -> dict[str, Any]:
    instantanea = lectura.instantanea
    energia = lectura.energia
    analitica = lectura.analitica

    return {
        "fecha_lectura": (instantanea.registrado_en.isoformat() if instantanea and instantanea.registrado_en else None),
        "potencia_activa_kw": (
            instantanea.potencia_activa_total_W / 1000
            if instantanea and instantanea.potencia_activa_total_W is not None
            else None
        ),
        "factor_potencia": (instantanea.factor_potencia_total if instantanea else None),
        "tension_linea_v": (instantanea.voltage_linea_V if instantanea else None),
        "thd_tension_pct": (instantanea.thd_v_promedio_pct if instantanea else None),
        "thd_corriente_pct": (instantanea.thd_i_total_pct if instantanea else None),
        "energia_activa_acumulada_kwh": (energia.net_active_energy_kwh if energia else None),
        "estado_factor_potencia": (
            analitica.estado_fp.value
            if analitica and hasattr(analitica.estado_fp, "value")
            else str(analitica.estado_fp)
            if analitica
            else None
        ),
        "estado_tension": (
            analitica.estado_tension.value
            if analitica and hasattr(analitica.estado_tension, "value")
            else str(analitica.estado_tension)
            if analitica
            else None
        ),
    }


def recopilar_telemetria(
    intencion: IntencionUsuario,
    organizacion_id: str,
    gestor_dispositivos: "GestionarDispositivosUseCase",
    consultar_telemetria: "ConsultarTelemetriaUseCase | None",
) -> dict[str, Any]:
    """Obtiene un resumen de telemetría de hasta 20 dispositivos."""
    if intencion != IntencionUsuario.RESUMEN_TELEMETRIA or consultar_telemetria is None:
        return {}

    dispositivos = gestor_dispositivos.listar_dispositivos(
        organizacion_id=organizacion_id,
    )
    resultados = {}
    limite = 20

    for dispositivo in dispositivos[:limite]:
        datos_dispositivo = dispositivo.model_dump(mode="json")
        device_id = datos_dispositivo.get("id") or datos_dispositivo.get("device_uid")

        if not device_id:
            logger.warning(
                "No se pudo consultar telemetría: falta el identificador de un dispositivo de la organización %s",
                organizacion_id,
            )
            continue

        try:
            lectura = consultar_telemetria.obtener_ultima_telemetria(
                device_id,
            )
        except Exception:
            logger.warning(
                "No se pudo obtener la última telemetría del dispositivo %s",
                device_id,
                exc_info=True,
            )
            continue

        resultados[device_id] = _construir_resumen_telemetria(lectura)

    if len(dispositivos) > limite:
        logger.info(
            "Se limitaron los datos de telemetría a %s de %s dispositivos para la organización %s",
            limite,
            len(dispositivos),
            organizacion_id,
        )

    return resultados
