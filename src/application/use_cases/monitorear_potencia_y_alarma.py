"""src/application/use_cases/monitorear_potencia_y_alarma.py."""

import logging
from datetime import datetime, timezone

from src.application.dtos.notificador_dto import NotificadorEstadoDTO
from src.domain.notificaciones.ports import PublicadorAlarmaPort
from src.domain.notificaciones.servicios.monitor_potencia_tuya import MonitorPotenciaTuyaService
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import BufferTelemetriaEnVivoPort, RepositorioOrganizacionesPort

logger = logging.getLogger(__name__)


class MonitorearPotenciaYAlarmaUseCase:
    """Monitorea potencia en vivo y controla alarma del GF-SMBOX-PLUS.

    Orquesta: lectura de potencia actual, evaluación de umbral, publicación de comando MQTT.
    """

    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        buffer_telemetria: BufferTelemetriaEnVivoPort,
        publisher: PublicadorAlarmaPort,
    ):
        self._repo_org = repo_organizaciones
        self._buffer = buffer_telemetria
        self._publisher = publisher
        self._servicio = MonitorPotenciaTuyaService()
        self._estado_alarma_anterior = False

    async def ejecutar(self, planta_id: str) -> NotificadorEstadoDTO:
        """Evalúa la alarma y publica comando si hay cambio de estado.

        Args:
            planta_id: ID de la planta a monitorear.

        Returns:
            DTO con estado actual de la alarma.

        Raises:
            PlantaNoEncontradaError: Si la planta no existe.
        """
        planta = self._repo_org.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada.")

        potencia_contratada_w = self._obtener_potencia_contratada(planta_id)

        potencia_adquirida_w = self._obtener_potencia_adquirida_viva(planta_id)
        if potencia_adquirida_w is None:
            logger.warning(f"No hay datos de potencia disponibles para planta {planta_id}")
            potencia_adquirida_w = 0.0

        resultado_eval = self._servicio.evaluar_alarma(
            potencia_adquirida_w=potencia_adquirida_w,
            potencia_contratada_w=potencia_contratada_w,
            alarma_sonora_activa=self._estado_alarma_anterior,
        )

        alarma_nueva = resultado_eval["alarma_activar"]

        if alarma_nueva != self._estado_alarma_anterior:
            exito = await self._publisher.publicar_alarma_sonora(alarma_nueva)
            if exito:
                self._estado_alarma_anterior = alarma_nueva
                logger.info(
                    f"Alarma {'activada' if alarma_nueva else 'desactivada'} ({resultado_eval['porcentaje_uso']:.1f}%)"
                )
            else:
                logger.error("Fallo al publicar comando de alarma")

        return NotificadorEstadoDTO(
            alarmaActiva=self._estado_alarma_anterior,
            potenciaAdquiridaW=potencia_adquirida_w,
            potenciaContratadaW=potencia_contratada_w,
            porcentajeUso=resultado_eval["porcentaje_uso"],
            ultimoEvento=datetime.now(timezone.utc),
        )

    def _obtener_potencia_contratada(self, planta_id: str) -> float:
        """Obtiene la potencia contratada punta de la última factura disponible.

        Args:
            planta_id: ID de la planta.

        Returns:
            Potencia contratada en watts. Retorna 0 si no hay facturas disponibles.
        """
        try:
            facturas = [f for f in self._repo_org.obtener_facturas_planta(planta_id) if f.tipo_dato == "potencia"]
            if not facturas:
                logger.warning(f"No hay facturas de potencia para planta {planta_id}")
                return 0.0

            factura = facturas[0]
            potencia_kw = factura.potencia_contratada_punta_kw or factura.potencia_contratada_fuera_punta_kw or 0.0
            return potencia_kw * 1000
        except Exception as e:
            logger.error(f"Error al obtener potencia contratada: {e}")
            return 0.0

    def _obtener_potencia_adquirida_viva(self, planta_id: str) -> float | None:
        """Obtiene la potencia activa instantánea en vivo de los medidores frontera.

        Args:
            planta_id: ID de la planta.

        Returns:
            Potencia en watts, o None si no hay datos.
        """
        try:
            nodos = self._repo_org.obtener_nodos_unifilar(planta_id)
            if not nodos:
                return None

            from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
            from src.domain.telemetria.value_objects import TipoNodoUnifilar

            arbol = ArbolUnifilarService(nodos)
            nodo_raiz = next(
                (n for n in nodos if n.tipo in (TipoNodoUnifilar.TGBT, TipoNodoUnifilar.TRANSFORMADOR)),
                None,
            ) or next((n for n in nodos if n.parent_id is None), None)

            if not nodo_raiz:
                return None

            medidores = arbol.medidores_frontera(nodo_raiz.id)
            if not medidores:
                return None

            potencia_total = 0.0
            for device_id in medidores:
                datos = self._buffer.obtener(device_id)
                if datos:
                    ultimo = datos[-1]
                    if "potencia_activa_total_w" in ultimo:
                        potencia_total += ultimo["potencia_activa_total_w"]

            return potencia_total if potencia_total > 0 else None

        except Exception as e:
            logger.error(f"Error al obtener potencia en vivo: {e}")
            return None
