"""src/domain/cargas/entities.py."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.domain.cargas.value_objects import (
    CategoriaCarga,
    EstadoCampana,
    FirmaCarga,
    MotivoDescarte,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    PatronOperacion,
    TipoCampana,
)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Carga:
    """Un consumo individual detrás de un medidor agregado.

    Deliberadamente genérica: acá una carga es una heladera o una pava, pero en una
    planta es un compresor o una línea de producción. Lo único que el motor necesita
    saber de ella es su firma eléctrica y su patrón temporal, que son los mismos
    conceptos en los dos casos.

    A diferencia de `Maquina` (disponibilidad), la relación con el dispositivo es
    N:1 — el medidor agregado ve muchas cargas a la vez, que es justamente el problema
    de desagregación.
    """

    id: str
    dispositivo_id: str
    nombre: str
    categoria: CategoriaCarga = CategoriaCarga.OTROS
    naturaleza_electrica: NaturalezaElectrica = NaturalezaElectrica.MIXTA
    patron_operacion: PatronOperacion = PatronOperacion.INDETERMINADO
    potencia_nominal_w: float | None = None
    firma: FirmaCarga | None = None
    activa: bool = True
    maquina_id: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)

    @property
    def esta_caracterizada(self) -> bool:
        """Sin firma el motor no puede atribuirle nada; la carga existe pero no juega."""
        return self.firma is not None

    @property
    def potencia_esperada_w(self) -> float | None:
        """Mejor estimación disponible: la firma medida gana siempre a la chapa."""
        if self.firma is not None:
            return self.firma.potencia_w
        return self.potencia_nominal_w


@dataclass
class CampanaCaracterizacion:
    """Una ventana acotada de medición a alta resolución sobre un medidor.

    Existe porque a la cadencia permanente de 5 minutos no se puede medir la firma de
    casi nada: un evento más corto que el intervalo de muestreo simplemente no fue
    medido, y ningún algoritmo puede recuperarlo. La campaña resuelve eso por
    instrumentación y no por matemática, poniendo el medidor en ráfaga durante una
    ventana corta y guardando todo lo que llega.

    `carga_id` es opcional: una campaña pasiva puede observar el conjunto de cargas
    autónomas de la casa sin apuntar a una sola.
    """

    id: str
    dispositivo_id: str
    tipo: TipoCampana
    inicio_at: datetime
    fin_planificado_at: datetime
    carga_id: str | None = None
    estado: EstadoCampana = EstadoCampana.EN_CURSO
    fin_at: datetime | None = None
    linea_base_w: float | None = None
    linea_base_var: float | None = None
    muestras: int = 0
    motivo_descarte: MotivoDescarte | None = None
    notas: str | None = None
    creado_por_usuario_id: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)

    @property
    def esta_en_curso(self) -> bool:
        return self.estado == EstadoCampana.EN_CURSO

    @property
    def duracion_planificada_s(self) -> float:
        return (self.fin_planificado_at - self.inicio_at).total_seconds()

    def esta_vencida(self, ahora: datetime | None = None) -> bool:
        """Vencida = pasó su fin planificado sin que nadie la cerrara.

        El cierre automático no es un detalle: una campaña olvidada dejaría al medidor
        publicando en ráfaga y escribiendo muestras indefinidamente.
        """
        return self.esta_en_curso and (ahora or ahora_utc()) >= self.fin_planificado_at

    def cerrar(
        self,
        estado: EstadoCampana,
        fin_at: datetime | None = None,
        motivo: MotivoDescarte | None = None,
        detalle: str | None = None,
    ) -> None:
        self.estado = estado
        self.fin_at = fin_at or ahora_utc()
        self.motivo_descarte = motivo
        if detalle is not None:
            self.notas = detalle


@dataclass
class IntervaloActividadCarga:
    """Un tramo en que se cree que una carga estuvo funcionando.

    `carga_id is None` significa `NO_ATRIBUIDO`: se detectó actividad real pero no se
    pudo decir de quién. Es información, no un hueco — el residual honesto es lo que
    permite saber cuánto del consumo queda sin explicar.

    Espeja a `EventoDisponibilidad` en el mecanismo de corrección humana, porque cumple
    el mismo rol: las filas corregidas a mano son el dataset etiquetado del que después
    puede salir un modelo, y por eso el motor batch nunca las pisa.
    """

    id: int | None
    dispositivo_id: str
    inicio_at: datetime
    fin_at: datetime
    carga_id: str | None = None
    potencia_media_w: float | None = None
    delta_reactiva_var: float | None = None
    energia_kwh: float | None = None
    confianza: float | None = None
    origen: OrigenClasificacionCarga = OrigenClasificacionCarga.REGLA
    corregido_por_usuario_id: str | None = None
    corregido_at: datetime | None = None
    notas: str | None = None

    @property
    def esta_atribuido(self) -> bool:
        return self.carga_id is not None

    @property
    def es_correccion_humana(self) -> bool:
        return self.origen == OrigenClasificacionCarga.CORRECCION_HUMANA

    @property
    def duracion_segundos(self) -> float:
        return max(0.0, round((self.fin_at - self.inicio_at).total_seconds(), 1))

    def corregir(
        self,
        carga_id: str | None,
        usuario_id: str,
        notas: str | None = None,
        ahora: datetime | None = None,
    ) -> None:
        """Reimputa el intervalo a mano. Queda marcado para que el batch no lo revierta."""
        self.carga_id = carga_id
        self.origen = OrigenClasificacionCarga.CORRECCION_HUMANA
        self.confianza = 1.0
        self.corregido_por_usuario_id = usuario_id
        self.corregido_at = ahora or ahora_utc()
        if notas is not None:
            self.notas = notas
