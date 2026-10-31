"""src/application/use_cases/gestionar_suscripciones.py."""

from datetime import datetime, timedelta

from src.domain.telemetria.entities import Suscripcion, ahora_utc
from src.domain.telemetria.exceptions import PlanNoEncontradoError
from src.domain.telemetria.ports import RepositorioPlanesPort, RepositorioSuscripcionesPort
from src.domain.telemetria.value_objects import ModoFreeTier


class GestionarSuscripcionesUseCase:
    """Ciclo de vida comercial de una organización: alta/extensión, cancelación y expiración.

    No conoce Mercado Pago ni ningún proveedor de pago — recibe organizacion_id/plan_id/fecha
    ya resueltos por el adaptador de pagos correspondiente (webhook, cron, o alta manual).
    """

    DIAS_GRACIA_POR_DEFECTO: int = 6
    """Ventana entre el vencimiento y la baja efectiva a modo_free (rango acordado: 5-7 días),
    para dar margen a los reintentos automáticos de cobro del proveedor de pagos."""

    def __init__(self, repo_suscripciones: RepositorioSuscripcionesPort, repo_planes: RepositorioPlanesPort) -> None:
        self.repo_suscripciones = repo_suscripciones
        self.repo_planes = repo_planes

    def activar_o_extender(self, organizacion_id: str, plan_id: str, hasta: datetime) -> Suscripcion:
        if self.repo_planes.obtener_por_id(plan_id) is None:
            raise PlanNoEncontradoError(f"Plan '{plan_id}' no existe en el catálogo.")
        actual = self.repo_suscripciones.obtener_por_organizacion(organizacion_id)
        modo_free = actual.modo_free if actual else ModoFreeTier.PRIVADO_BASICO
        return self.repo_suscripciones.guardar(
            Suscripcion(
                organizacion_id=organizacion_id,
                plan_id=plan_id,
                pro_vence_en=hasta,
                modo_free=modo_free,
            )
        )

    def cancelar(self, organizacion_id: str, modo_free: ModoFreeTier = ModoFreeTier.PRIVADO_BASICO) -> Suscripcion:
        """Baja inmediata (ej. webhook de cancelación explícita), sin esperar el vencimiento."""
        actual = self.repo_suscripciones.obtener_por_organizacion(organizacion_id)
        plan_id = actual.plan_id if actual else None
        return self.repo_suscripciones.guardar(
            Suscripcion(
                organizacion_id=organizacion_id,
                plan_id=plan_id,
                pro_vence_en=None,
                modo_free=modo_free,
            )
        )

    def expirar_vencidas(self, ahora: datetime | None = None, dias_gracia: int | None = None) -> list[Suscripcion]:
        """Baja a `PRIVADO_BASICO` toda suscripción cuyo `pro_vence_en` pasó hace más de
        `dias_gracia` días. Pensado para correr desde un cron/systemd-timer (ver
        `scripts/expirar_suscripciones.py`).
        """
        ahora = ahora or ahora_utc()
        gracia = self.DIAS_GRACIA_POR_DEFECTO if dias_gracia is None else dias_gracia
        corte = ahora - timedelta(days=gracia)
        vencidas = self.repo_suscripciones.listar_vencidas(corte)
        return [self.cancelar(s.organizacion_id) for s in vencidas]
