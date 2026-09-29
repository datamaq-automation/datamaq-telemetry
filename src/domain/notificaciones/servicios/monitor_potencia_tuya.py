"""src/domain/notificaciones/servicios/monitor_potencia_tuya.py."""


class MonitorPotenciaTuyaService:
    """Servicio que evalúa alarmas de potencia con histéresis."""

    UMBRAL_ACTIVACION = 90.0
    UMBRAL_DESACTIVACION = 85.0

    def evaluar_alarma(
        self,
        potencia_adquirida_w: float,
        potencia_contratada_w: float,
        alarma_sonora_activa: bool,
    ) -> dict:
        """Evalúa si debe activarse/desactivarse la alarma usando histéresis.

        Args:
            potencia_adquirida_w: Potencia adquirida en watts.
            potencia_contratada_w: Potencia contratada en watts.
            alarma_sonora_activa: Estado actual de la alarma.

        Returns:
            Dict con decisión de alarma y valores actuales.
        """
        if potencia_contratada_w <= 0:
            return {
                "alarma_activar": False,
                "potencia_adquirida_w": potencia_adquirida_w,
                "potencia_contratada_w": potencia_contratada_w,
                "porcentaje_uso": 0.0,
            }

        porcentaje = (potencia_adquirida_w / potencia_contratada_w) * 100

        if porcentaje >= self.UMBRAL_ACTIVACION:
            alarma_nueva = True
        elif porcentaje < self.UMBRAL_DESACTIVACION:
            alarma_nueva = False
        else:
            alarma_nueva = alarma_sonora_activa

        return {
            "alarma_activar": alarma_nueva,
            "potencia_adquirida_w": potencia_adquirida_w,
            "potencia_contratada_w": potencia_contratada_w,
            "porcentaje_uso": porcentaje,
        }
