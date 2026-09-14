"""src/infrastructure/paho_mqtt/verificador_notificaciones.py.

Decide si corresponde notificar (email) una alerta crítica de un dispositivo, según el
estado comercial de la organización dueña de la planta. Fase 2 del plan de billing:
organizaciones en `modo_free` (PRO no vigente) no reciben notificaciones de alertas.

Mismo criterio que `ConsultarTelemetriaUseCase._suscripcion_de_dispositivo`: si no se puede
resolver una organización para el dispositivo (dispositivos de desarrollo/sin planta), no se
restringe — se asume no comercial y se notifica igual.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from src.domain.telemetria.entities import Suscripcion
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.servicios.politicas_suscripcion import PoliticaSuscripcionService
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLDispositivosRepository
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def construir_verificador_notificaciones(
    session_factory: sessionmaker,
    repo_organizaciones: RepositorioOrganizacionesPort | None = None,
) -> Callable[[str], bool]:
    """Cada llamada abre y cierra su propia sesión: se registra una sola vez a nivel proceso
    (`ProcesadorAlertasIngesta.configurar_notificador`) pero se invoca por mensaje MQTT desde
    varios threads del pool, así que no puede compartir estado ni sesión con nadie más.

    `repo_organizaciones` es inyectable para tests; en producción es YAML (dato maestro)."""

    repo_org = repo_organizaciones or YamlOrganizacionesRepository()

    def _notificaciones_habilitadas_para(dispositivo_id: str) -> bool:
        db = session_factory()
        try:
            repo_disp = MySQLDispositivosRepository(db)
            repo_sus = MySQLSuscripcionesRepository(db)

            dev = repo_disp.obtener_por_id(dispositivo_id)
            if not dev or not dev.planta_id:
                return True
            planta = repo_org.obtener_planta_por_id(dev.planta_id)
            if not planta or not planta.organizacion_id:
                return True
            if repo_org.obtener_por_id(planta.organizacion_id) is None:
                return True

            sus = repo_sus.obtener_por_organizacion(planta.organizacion_id) or Suscripcion.por_defecto(
                planta.organizacion_id
            )
            return PoliticaSuscripcionService.es_pro_vigente(sus.pro_vence_en, datetime.now(timezone.utc))
        finally:
            db.close()

    return _notificaciones_habilitadas_para
