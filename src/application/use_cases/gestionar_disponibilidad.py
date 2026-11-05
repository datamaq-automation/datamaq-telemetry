"""src/application/use_cases/gestionar_disponibilidad.py."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from src.application.dtos.disponibilidad_dto import (
    CorregirClasificacionRequestDTO,
    EventoDisponibilidadResponseDTO,
    MetricasDisponibilidadOEEResponseDTO,
    ParadaProgramadaCreateDTO,
    ParadaProgramadaResponseDTO,
)
from src.application.mappers.disponibilidad_mapper import (
    EventoDisponibilidadMapper,
    ParadaProgramadaMapper,
)
from src.domain.disponibilidad.entities import EventoDisponibilidad, ParadaProgramada
from src.domain.disponibilidad.exceptions import (
    DispositivoDeOrganizacionDistintaError,
    EventoDisponibilidadNoEncontradoError,
    MaquinaNoEncontradaError,
    RangoParadaProgramadaInvalidoError,
)
from src.domain.disponibilidad.ports import (
    RepositorioEventosDisponibilidadPort,
    RepositorioMaquinasPort,
    RepositorioParadasProgramadasPort,
)
from src.domain.disponibilidad.services import (
    CalculadorMetricasOEEService,
    ClasificadorDisponibilidadService,
    FiltroPersistenciaEstadoService,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina, TipoParada
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioOrganizacionesPort


class GestionarDisponibilidadUseCase:
    """Clasifica disponibilidad de máquina y gestiona correcciones humanas y paradas programadas.

    `clasificar_lectura` recibe cada lectura de potencia entrante (llamado desde
    `IngestarTelemetriaUseCase`, análogo a como se evalúan las alertas de calidad de
    energía) y usa un `FiltroPersistenciaEstadoService` compartido entre invocaciones
    para no reaccionar a un pico transitorio, con la ventana de persistencia propia de
    cada `Maquina`.
    """

    _filtro_persistencia: ClassVar[FiltroPersistenciaEstadoService] = FiltroPersistenciaEstadoService()

    def __init__(
        self,
        repo_maquinas: RepositorioMaquinasPort,
        repo_eventos: RepositorioEventosDisponibilidadPort,
        repo_paradas: RepositorioParadasProgramadasPort,
        repo_dispositivos: RepositorioDispositivosPort | None = None,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
    ) -> None:
        self.repo_maquinas = repo_maquinas
        self.repo_eventos = repo_eventos
        self.repo_paradas = repo_paradas
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones

    def _validar_maquina_en_organizacion(self, maquina_id: str, organizacion_id: str) -> None:
        if not self.repo_dispositivos or not self.repo_organizaciones:
            return
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if maquina is None:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")
        dispositivo = self.repo_dispositivos.obtener_por_id(maquina.dispositivo_id)
        planta = (
            self.repo_organizaciones.obtener_planta_por_id(dispositivo.planta_id)
            if dispositivo and dispositivo.planta_id
            else None
        )
        if not planta or planta.organizacion_id != organizacion_id:
            raise DispositivoDeOrganizacionDistintaError(
                f"La máquina '{maquina_id}' no pertenece a la organización del usuario."
            )

    def clasificar_lectura(self, dispositivo_id: str, potencia_w: float, recorded_at: datetime) -> None:
        """No-op si el dispositivo no tiene una `Maquina` asociada o no está calibrada todavía."""
        maquina = self.repo_maquinas.obtener_por_dispositivo_id(dispositivo_id)
        if maquina is None or maquina.umbral_marcha_w is None:
            return
        umbral_marcha_w = maquina.umbral_marcha_w

        estado_candidato = ClasificadorDisponibilidadService.evaluar(potencia_w, umbral_marcha_w)
        evento_abierto = self.repo_eventos.obtener_evento_abierto(maquina.id)
        estado_confirmado = evento_abierto.estado if evento_abierto else None

        debe_confirmar = self._filtro_persistencia.confirmar_cambio(
            maquina.id,
            estado_confirmado,
            estado_candidato,
            maquina.ventana_persistencia_lecturas,
            maquina.ventana_persistencia_segundos,
            recorded_at,
        )
        if not debe_confirmar:
            return
        nuevo_estado = estado_candidato

        if evento_abierto is not None:
            evento_abierto.cerrar(recorded_at, potencia_promedio_w=potencia_w)
            self.repo_eventos.guardar(evento_abierto)

        tipo_parada = None
        if nuevo_estado == EstadoMaquina.PARADA:
            parada_vigente = self.repo_paradas.buscar_vigente(maquina.id, recorded_at)
            tipo_parada = TipoParada.PROGRAMADA if parada_vigente else TipoParada.SIN_CLASIFICAR

        nuevo_evento = EventoDisponibilidad(
            id=None,
            maquina_id=maquina.id,
            estado=nuevo_estado,
            inicio_at=recorded_at,
            tipo_parada=tipo_parada,
            potencia_promedio_w=potencia_w,
        )
        self.repo_eventos.guardar(nuevo_evento)

    def listar_eventos(self, maquina_id: str, limite: int = 100) -> list[EventoDisponibilidadResponseDTO]:
        eventos = self.repo_eventos.listar_por_maquina(maquina_id, limite=limite)
        return [EventoDisponibilidadMapper.to_dto(e) for e in eventos]

    def corregir_clasificacion(
        self, evento_id: int, dto: CorregirClasificacionRequestDTO, usuario_id: str
    ) -> EventoDisponibilidadResponseDTO:
        evento = self.repo_eventos.obtener_por_id(evento_id)
        if not evento:
            raise EventoDisponibilidadNoEncontradoError(f"Evento de disponibilidad {evento_id} no encontrado.")

        evento.marcar_correccion_manual(
            TipoParada(dto.tipo_parada),
            usuario_id=usuario_id,
            comentario=dto.comentario,
            ahora=datetime.now(timezone.utc),
        )
        saved = self.repo_eventos.guardar(evento)
        return EventoDisponibilidadMapper.to_dto(saved)

    def registrar_parada_programada(
        self, dto: ParadaProgramadaCreateDTO, usuario_id: str | None, organizacion_id: str | None = None
    ) -> ParadaProgramadaResponseDTO:
        if organizacion_id is not None:
            self._validar_maquina_en_organizacion(dto.maquina_id, organizacion_id)
        if dto.fin_at <= dto.inicio_at:
            raise RangoParadaProgramadaInvalidoError("El fin de la parada programada debe ser posterior al inicio.")

        entity = ParadaProgramada(
            id=str(uuid.uuid4()),
            maquina_id=dto.maquina_id,
            inicio_at=dto.inicio_at,
            fin_at=dto.fin_at,
            motivo=dto.motivo,
            creado_por_usuario_id=usuario_id,
        )
        saved = self.repo_paradas.guardar(entity)
        return ParadaProgramadaMapper.to_dto(saved)

    def listar_paradas_programadas(self, maquina_id: str) -> list[ParadaProgramadaResponseDTO]:
        paradas = self.repo_paradas.listar_por_maquina(maquina_id)
        return [ParadaProgramadaMapper.to_dto(p) for p in paradas]

    def calcular_metricas_oee(
        self,
        maquina_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        dias: int = 7,
    ) -> MetricasDisponibilidadOEEResponseDTO:
        maquina = self.repo_maquinas.obtener_por_id(maquina_id)
        if not maquina:
            raise MaquinaNoEncontradaError(f"Máquina '{maquina_id}' no encontrada.")

        fin = hasta or datetime.now(timezone.utc)
        inicio = desde or (fin - timedelta(days=dias))

        eventos = self.repo_eventos.listar_por_rango(maquina_id, inicio, fin)
        metricas = CalculadorMetricasOEEService.calcular_metricas(eventos, inicio=inicio, fin=fin)

        return MetricasDisponibilidadOEEResponseDTO(
            maquina_id=maquina_id,
            periodo_inicio=inicio,
            periodo_fin=fin,
            tiempo_total_segundos=metricas.tiempo_total_s,
            tiempo_marcha_segundos=metricas.tiempo_marcha_s,
            tiempo_parada_programada_segundos=metricas.tiempo_parada_programada_s,
            tiempo_parada_no_programada_segundos=metricas.tiempo_parada_no_programada_s,
            disponibilidad_oee_porcentaje=metricas.disponibilidad_oee_pct,
            mtbf_horas=metricas.mtbf_horas,
            mttr_horas=metricas.mttr_horas,
            cantidad_paradas_no_programadas=metricas.cantidad_paradas_no_programadas,
            cantidad_paradas_programadas=metricas.cantidad_paradas_programadas,
            cantidad_ciclos_marcha=metricas.cantidad_ciclos_marcha,
        )
