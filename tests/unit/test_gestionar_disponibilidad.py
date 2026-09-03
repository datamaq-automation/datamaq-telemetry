"""Caso de uso GestionarDisponibilidadUseCase: clasificación por evento, persistencia anti-transitorios,
corrección humana y cruce con paradas programadas — todo con repositorios fake en memoria."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.dtos.disponibilidad_dto import (
    CorregirClasificacionRequestDTO,
    ParadaProgramadaCreateDTO,
)
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.domain.disponibilidad.entities import EventoDisponibilidad, Maquina, ParadaProgramada
from src.domain.disponibilidad.exceptions import (
    EventoDisponibilidadNoEncontradoError,
    RangoParadaProgramadaInvalidoError,
)
from src.domain.disponibilidad.ports import (
    RepositorioEventosDisponibilidadPort,
    RepositorioMaquinasPort,
    RepositorioParadasProgramadasPort,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina, OrigenClasificacion, TipoParada


class _FakeMaquinasRepo(RepositorioMaquinasPort):
    def __init__(self):
        self.maquinas: dict[str, Maquina] = {}

    def obtener_por_id(self, maquina_id):
        return self.maquinas.get(maquina_id)

    def obtener_por_dispositivo_id(self, dispositivo_id):
        return next((m for m in self.maquinas.values() if m.dispositivo_id == dispositivo_id), None)

    def listar(self):
        return list(self.maquinas.values())

    def guardar(self, maquina):
        self.maquinas[maquina.id] = maquina
        return maquina


class _FakeEventosRepo(RepositorioEventosDisponibilidadPort):
    def __init__(self):
        self.eventos: dict[int, EventoDisponibilidad] = {}
        self._next_id = 1

    def obtener_por_id(self, evento_id):
        return self.eventos.get(evento_id)

    def obtener_evento_abierto(self, maquina_id):
        abiertos = [e for e in self.eventos.values() if e.maquina_id == maquina_id and e.esta_abierto]
        return max(abiertos, key=lambda e: e.inicio_at) if abiertos else None

    def listar_por_maquina(self, maquina_id, limite=100):
        items = [e for e in self.eventos.values() if e.maquina_id == maquina_id]
        return sorted(items, key=lambda e: e.inicio_at, reverse=True)[:limite]

    def guardar(self, evento):
        if evento.id is None:
            evento.id = self._next_id
            self._next_id += 1
        self.eventos[evento.id] = evento
        return evento


class _FakeParadasRepo(RepositorioParadasProgramadasPort):
    def __init__(self):
        self.paradas: list[ParadaProgramada] = []

    def guardar(self, parada):
        self.paradas.append(parada)
        return parada

    def listar_por_maquina(self, maquina_id):
        return [p for p in self.paradas if p.maquina_id == maquina_id]

    def buscar_vigente(self, maquina_id, instante):
        return next((p for p in self.paradas if p.maquina_id == maquina_id and p.incluye(instante)), None)


def _fecha(segundos: float = 0.0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=segundos)


@pytest.fixture(autouse=True)
def _limpiar_filtro_compartido():
    GestionarDisponibilidadUseCase._filtro_persistencia.limpiar()
    yield
    GestionarDisponibilidadUseCase._filtro_persistencia.limpiar()


def _use_case() -> tuple[GestionarDisponibilidadUseCase, _FakeMaquinasRepo, _FakeEventosRepo, _FakeParadasRepo]:
    repo_maq = _FakeMaquinasRepo()
    repo_eventos = _FakeEventosRepo()
    repo_paradas = _FakeParadasRepo()
    return GestionarDisponibilidadUseCase(repo_maq, repo_eventos, repo_paradas), repo_maq, repo_eventos, repo_paradas


def test_clasificar_lectura_es_no_op_sin_maquina_asociada():
    use_case, _, repo_eventos, _ = _use_case()
    use_case.clasificar_lectura("dev-sin-maquina", 500.0, _fecha(0))
    assert repo_eventos.eventos == {}


def test_clasificar_lectura_es_no_op_sin_calibrar():
    use_case, repo_maq, repo_eventos, _ = _use_case()
    repo_maq.guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))  # umbral_marcha_w=None

    use_case.clasificar_lectura("dev-1", 500.0, _fecha(0))

    assert repo_eventos.eventos == {}


def test_clasificar_lectura_abre_evento_solo_tras_persistencia_confirmada():
    use_case, repo_maq, repo_eventos, _ = _use_case()
    repo_maq.guardar(
        Maquina(
            id="maq-1",
            dispositivo_id="dev-1",
            nombre="Línea 1",
            umbral_marcha_w=100.0,
            ventana_persistencia_lecturas=2,
            ventana_persistencia_segundos=999.0,
        )
    )

    # 1ra lectura de marcha: transitorio posible, no confirma todavía.
    use_case.clasificar_lectura("dev-1", 500.0, _fecha(0))
    assert repo_eventos.obtener_evento_abierto("maq-1") is None

    # 2da lectura consecutiva: confirma el cambio y abre el evento.
    use_case.clasificar_lectura("dev-1", 500.0, _fecha(1))
    abierto = repo_eventos.obtener_evento_abierto("maq-1")
    assert abierto is not None
    assert abierto.estado == EstadoMaquina.MARCHA
    assert abierto.origen == OrigenClasificacion.REGLA


def test_clasificar_lectura_cierra_evento_previo_al_confirmar_parada():
    use_case, repo_maq, repo_eventos, _ = _use_case()
    repo_maq.guardar(
        Maquina(
            id="maq-1",
            dispositivo_id="dev-1",
            nombre="Línea 1",
            umbral_marcha_w=100.0,
            ventana_persistencia_lecturas=2,
            ventana_persistencia_segundos=999.0,
        )
    )
    use_case.clasificar_lectura("dev-1", 500.0, _fecha(0))
    use_case.clasificar_lectura("dev-1", 500.0, _fecha(1))
    evento_marcha = repo_eventos.obtener_evento_abierto("maq-1")
    assert evento_marcha is not None

    # Un único dip no confirma el cambio a parada (persistencia = 2 lecturas).
    use_case.clasificar_lectura("dev-1", 10.0, _fecha(2))
    assert repo_eventos.obtener_evento_abierto("maq-1").id == evento_marcha.id

    # Segunda lectura baja consecutiva: confirma, cierra marcha y abre parada.
    use_case.clasificar_lectura("dev-1", 10.0, _fecha(3))

    cerrado = repo_eventos.obtener_por_id(evento_marcha.id)
    assert cerrado.fin_at == _fecha(3)
    assert cerrado.esta_abierto is False

    nuevo_abierto = repo_eventos.obtener_evento_abierto("maq-1")
    assert nuevo_abierto is not None
    assert nuevo_abierto.id != evento_marcha.id
    assert nuevo_abierto.estado == EstadoMaquina.PARADA
    assert nuevo_abierto.tipo_parada == TipoParada.SIN_CLASIFICAR


def test_clasificar_lectura_parada_dentro_de_ventana_programada_se_marca_programada():
    use_case, repo_maq, repo_eventos, repo_paradas = _use_case()
    repo_maq.guardar(
        Maquina(
            id="maq-1",
            dispositivo_id="dev-1",
            nombre="Línea 1",
            umbral_marcha_w=100.0,
            ventana_persistencia_lecturas=1,
            ventana_persistencia_segundos=0.0,
        )
    )
    repo_paradas.guardar(
        ParadaProgramada(
            id="parada-1",
            maquina_id="maq-1",
            inicio_at=_fecha(0),
            fin_at=_fecha(100),
            motivo="Mantenimiento programado",
        )
    )

    use_case.clasificar_lectura("dev-1", 10.0, _fecha(10))

    abierto = repo_eventos.obtener_evento_abierto("maq-1")
    assert abierto is not None
    assert abierto.estado == EstadoMaquina.PARADA
    assert abierto.tipo_parada == TipoParada.PROGRAMADA


def test_corregir_clasificacion_marca_origen_humano():
    use_case, repo_maq, repo_eventos, _ = _use_case()
    repo_maq.guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1", umbral_marcha_w=100.0))
    evento = repo_eventos.guardar(
        EventoDisponibilidad(
            id=None,
            maquina_id="maq-1",
            estado=EstadoMaquina.PARADA,
            tipo_parada=TipoParada.SIN_CLASIFICAR,
            inicio_at=_fecha(0),
        )
    )

    dto = CorregirClasificacionRequestDTO(tipo_parada="PROGRAMADA", comentario="Cambio de turno no cargado")
    resultado = use_case.corregir_clasificacion(evento.id, dto, usuario_id="user-1")

    assert resultado.tipo_parada == "PROGRAMADA"
    assert resultado.origen == "CORRECCION_HUMANA"
    assert resultado.comentario == "Cambio de turno no cargado"


def test_corregir_clasificacion_evento_inexistente_lanza_excepcion():
    use_case, *_ = _use_case()
    dto = CorregirClasificacionRequestDTO(tipo_parada="PROGRAMADA")
    with pytest.raises(EventoDisponibilidadNoEncontradoError):
        use_case.corregir_clasificacion(999, dto, usuario_id="user-1")


def test_registrar_parada_programada_valida_rango():
    use_case, *_ = _use_case()
    dto = ParadaProgramadaCreateDTO(
        maquina_id="maq-1", inicio_at=_fecha(10), fin_at=_fecha(5), motivo="Fin antes que inicio"
    )
    with pytest.raises(RangoParadaProgramadaInvalidoError):
        use_case.registrar_parada_programada(dto, usuario_id="user-1")


def test_registrar_parada_programada_ok():
    use_case, *_ = _use_case()
    dto = ParadaProgramadaCreateDTO(
        maquina_id="maq-1", inicio_at=_fecha(0), fin_at=_fecha(3600), motivo="Mantenimiento preventivo"
    )
    resultado = use_case.registrar_parada_programada(dto, usuario_id="user-1")

    assert resultado.maquina_id == "maq-1"
    assert resultado.motivo == "Mantenimiento preventivo"
    assert resultado.creado_por_usuario_id == "user-1"
