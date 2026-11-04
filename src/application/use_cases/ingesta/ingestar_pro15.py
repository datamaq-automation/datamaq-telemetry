"""src/application/use_cases/ingesta/ingestar_pro15.py — ingesta del Powermeter Pro15 (multimedidor).

Un topic `pro15/{MAC}/{sub}/v1` trae un bloque por medidor interno (id 0, 1, …). Cada bloque se resuelve a
su propia fila (MAC, medidor_id) y se despacha con la misma lógica que el resto de la ingesta.

Ver specs/ingesta-pro15-multimedidor.md. `onoff` solo actualiza el equipo (medidor 0); `status` se trata como
en el resto de equipos (log de estado del medidor 0).
"""

from datetime import datetime, timezone
from typing import Any

from src.application.mappers.payload_telemetria_parser import TelemetriaPayloadParser
from src.application.use_cases.ingesta.resolvedor_dispositivo import ResolvedorDispositivoIngesta
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import (
    LoggerPort,
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.servicios.pro15_payload import (
    bloques_por_subtopico,
    device_info_pro15_a_formato_ingesta,
    parsear_topico_pro15,
)
from src.domain.telemetria.value_objects import MacAddress

MODELO_PRO15_POR_DEFECTO = "Smart Pro15"


class IngestarPro15UseCase:
    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        telemetria: IngestarTelemetriaUseCase,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
        permitir_auto_registro: bool = True,
    ) -> None:
        self.repo_dispositivos = repo_dispositivos
        self.repo_telemetria = repo_telemetria
        self.telemetria = telemetria
        self.publicador = publicador
        self.logger = logger
        self.permitir_auto_registro = permitir_auto_registro

    def ejecutar(self, topico: str, payload: Any) -> None:
        topico_pro15 = parsear_topico_pro15(topico)
        if topico_pro15 is None:
            return
        mac = topico_pro15.mac
        subtopico = topico_pro15.subtopico
        # Nunca se registra como SmartPlus: si llega `inst` antes que `onoff`, el modelo sale del topic
        # (Smart Pro15). `onoff` completa después el firmware y el número de serie.
        dev_info = {
            "device_model": MODELO_PRO15_POR_DEFECTO,
            **(
                device_info_pro15_a_formato_ingesta(payload.get("device_info") if isinstance(payload, dict) else None)
                or {}
            ),
        }

        if subtopico in ("onoff", "status") and isinstance(payload, dict):
            # Equipo completo (medidor 0): onoff actualiza el equipo; status va como log de estado del medidor 0.
            ahora = self._ahora(payload.get("power_on") or payload.get("time"))
            disp = self._resolver(mac, dev_info, ahora, medidor_id=0)
            if disp is None:
                return
            if subtopico == "status":
                recorded_at = ahora
                self.telemetria.procesar_con_dispositivo(topico, mac, subtopico, payload, disp, recorded_at)
            return

        for bloque in bloques_por_subtopico(subtopico, payload):
            recorded_at = TelemetriaPayloadParser.parse_timestamp(bloque.timestamp)
            disp = self._resolver(mac, dev_info, recorded_at, medidor_id=bloque.medidor_id)
            if disp is None:
                continue
            self.telemetria.procesar_con_dispositivo(topico, mac, subtopico, bloque.datos, disp, recorded_at)

    def _resolver(
        self, mac: str, dev_info: dict[str, Any] | None, ahora: datetime, medidor_id: int
    ) -> Dispositivo | None:
        return ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
            mac_raw=MacAddress(mac).valor,
            dev_info=dev_info,
            ahora=ahora,
            repo_dispositivos=self.repo_dispositivos,
            permitir_auto_registro=self.permitir_auto_registro,
            logger=self.logger,
            medidor_id=medidor_id,
        )

    @staticmethod
    def _ahora(valor: Any) -> datetime:
        try:
            return TelemetriaPayloadParser.parse_timestamp(valor)
        except Exception:
            return datetime.now(timezone.utc)
