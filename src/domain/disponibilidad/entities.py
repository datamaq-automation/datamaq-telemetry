from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.domain.disponibilidad.value_objects import EstadoMaquina, OrigenClasificacion, TipoParada


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Maquina:
    id: str
    dispositivo_id: str
    nombre: str
    umbral_marcha_w: float | None = None
    ventana_persistencia_lecturas: int = 2
    ventana_persistencia_segundos: float = 60.0
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)

    @property
    def esta_calibrada(self) -> bool:
        return self.umbral_marcha_w is not None


@dataclass
class EventoDisponibilidad:
    id: int | None
    maquina_id: str
    estado: EstadoMaquina
    inicio_at: datetime
    fin_at: datetime | None = None
    tipo_parada: TipoParada | None = None
    potencia_promedio_w: float | None = None
    origen: OrigenClasificacion = OrigenClasificacion.REGLA
    corregido_por_usuario_id: str | None = None
    corregido_at: datetime | None = None
    comentario: str | None = None

    @property
    def esta_abierto(self) -> bool:
        return self.fin_at is None

    @property
    def duracion_segundos(self) -> float | None:
        if self.fin_at is None:
            return None
        return max(0.0, round((self.fin_at - self.inicio_at).total_seconds(), 1))

    def cerrar(self, fin_at: datetime, potencia_promedio_w: float | None = None) -> None:
        self.fin_at = fin_at
        if potencia_promedio_w is not None:
            self.potencia_promedio_w = potencia_promedio_w

    def marcar_correccion_manual(
        self,
        tipo_parada: TipoParada,
        usuario_id: str,
        comentario: str | None = None,
        ahora: datetime | None = None,
    ) -> None:
        self.tipo_parada = tipo_parada
        self.origen = OrigenClasificacion.CORRECCION_HUMANA
        self.corregido_por_usuario_id = usuario_id
        self.corregido_at = ahora or ahora_utc()
        if comentario is not None:
            self.comentario = comentario


@dataclass
class ParadaProgramada:
    id: str
    maquina_id: str
    inicio_at: datetime
    fin_at: datetime
    motivo: str
    creado_por_usuario_id: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)

    def incluye(self, instante: datetime) -> bool:
        return self.inicio_at <= instante <= self.fin_at
