"""src/infrastructure/sqlalchemy/mysql_repositories.py — Fachada de compatibilidad hacia atrás para los repositorios MySQL de SQLAlchemy.

Las implementaciones concretas han sido modularizadas en el paquete
`src.infrastructure.sqlalchemy.repositories` siguiendo principios de
Single Responsibility (SRP) y Screaming Architecture.
"""

from src.infrastructure.sqlalchemy.repositories.accesos_planta_repository import (
    MySQLAccesosPlantaRepository,
)
from src.infrastructure.sqlalchemy.repositories.auditoria_repository import (
    MySQLAuditoriaRepository,
)
from src.infrastructure.sqlalchemy.repositories.ensayos_repository import (
    MySQLCampanasRepository,
)
from src.infrastructure.sqlalchemy.repositories.cargas_repository import (
    MySQLMáquinasRepository,
    MySQLSeriePotenciaRepository,
)
from src.infrastructure.sqlalchemy.repositories.disponibilidad_repository import (
    MySQLEventosDisponibilidadRepository,
    MySQLMaquinasRepository,
    MySQLParadasProgramadasRepository,
)
from src.infrastructure.sqlalchemy.repositories.dispositivos_confiables_repository import (
    MySQLDispositivosConfiablesRepository,
)
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (
    MySQLDispositivosRepository,
)
from src.infrastructure.sqlalchemy.repositories.intervalos_repository import (
    MySQLIntervalosActividadRepository,
)
from src.infrastructure.sqlalchemy.repositories.planes_repository import (
    MySQLPlanesRepository,
)
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import (
    MySQLSuscripcionesRepository,
)
from src.infrastructure.sqlalchemy.repositories.telemetria_repository import (
    MySQLTelemetriaRepository,
)
from src.infrastructure.sqlalchemy.repositories.usuarios_repository import (
    MySQLUsuariosRepository,
)
from src.infrastructure.sqlalchemy.repositories.webhook_events_repository import (
    MySQLRegistroEventosWebhook,
)

__all__ = [
    "MySQLAccesosPlantaRepository",
    "MySQLAuditoriaRepository",
    "MySQLCampanasRepository",
    "MySQLMáquinasRepository",
    "MySQLDispositivosConfiablesRepository",
    "MySQLDispositivosRepository",
    "MySQLEventosDisponibilidadRepository",
    "MySQLIntervalosActividadRepository",
    "MySQLMaquinasRepository",
    "MySQLParadasProgramadasRepository",
    "MySQLPlanesRepository",
    "MySQLRegistroEventosWebhook",
    "MySQLSeriePotenciaRepository",
    "MySQLSuscripcionesRepository",
    "MySQLTelemetriaRepository",
    "MySQLUsuariosRepository",
]
