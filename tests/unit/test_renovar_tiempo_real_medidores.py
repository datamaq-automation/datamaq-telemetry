"""tests/unit/test_renovar_tiempo_real_medidores.py — Renovación de tiempo real acotada a quien mira en vivo (#15).

Antes, con un solo WebSocket conectado se mandaba `realtime_sync_mode` cada ~75 s a todos los medidores de la
tabla `devices`, de cualquier organización y aunque estuvieran caídos.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.use_cases.renovar_tiempo_real_medidores import (
    SEGUNDOS_TIEMPO_REAL,
    RenovarTiempoRealMedidoresUseCase,
)
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.servicios.alcance_tiempo_real import (
    VENTANA_RECEPCION_RECIENTE_S,
    AlcanceTiempoReal,
    alcance_de_clientes,
)
from src.domain.telemetria.value_objects import MacAddress

AHORA = datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc)
RECIENTE = AHORA - timedelta(seconds=90)
CAIDO = AHORA - timedelta(seconds=VENTANA_RECEPCION_RECIENTE_S + 1)


def _disp(id_: str, mac: str, visto: datetime | None = RECIENTE) -> Dispositivo:
    return Dispositivo(id=id_, device_uid=MacAddress(mac), nombre=id_, visto_por_ultima_vez=visto)


class _RepoDisp:
    def __init__(self, por_org: dict[str, list[Dispositivo]], sin_org: list[Dispositivo] | None = None) -> None:
        self.por_org = por_org
        self.sin_org = sin_org or []
        self.llamadas: list[str | None] = []

    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        self.llamadas.append(organizacion_id)
        if organizacion_id is None:
            return [d for ds in self.por_org.values() for d in ds] + self.sin_org
        return list(self.por_org.get(organizacion_id, []))


class _Comando:
    def __init__(self, resultado: bool = True) -> None:
        self.resultado = resultado
        self.enviados: list[tuple[str, int]] = []

    def activar_rafaga(self, device_uid: str, segundos: int) -> bool:
        self.enviados.append((device_uid, segundos))
        return self.resultado


def _repo() -> _RepoDisp:
    return _RepoDisp(
        {
            "org-a": [_disp("a1", "AAAAAAAAAA01"), _disp("a2", "AAAAAAAAAA02", visto=CAIDO)],
            "org-b": [_disp("b1", "BBBBBBBBBB01")],
        },
        sin_org=[_disp("x1", "CCCCCCCCCC01")],
    )


def _ejecutar(alcance: AlcanceTiempoReal, repo: _RepoDisp | None = None, comando: _Comando | None = None) -> Any:
    repo = repo or _repo()
    comando = comando or _Comando()
    resultado = RenovarTiempoRealMedidoresUseCase(repo, comando).ejecutar(alcance, AHORA)
    return resultado, repo, comando


# --- Caso de uso ---


def test_organizacion_conectada_renueva_solo_sus_medidores_en_linea():
    resultado, repo, comando = _ejecutar(alcance_de_clientes([(False, "org-a")]))
    assert comando.enviados == [("AAAAAAAAAA01", SEGUNDOS_TIEMPO_REAL)]
    assert repo.llamadas == ["org-a"]
    assert (resultado.renovados, resultado.omitidos_sin_recepcion_reciente) == (1, 1)


def test_superadmin_renueva_todos_los_medidores_en_linea_incluso_sin_planta():
    resultado, repo, comando = _ejecutar(alcance_de_clientes([(True, None)]))
    assert sorted(uid for uid, _ in comando.enviados) == ["AAAAAAAAAA01", "BBBBBBBBBB01", "CCCCCCCCCC01"]
    assert repo.llamadas == [None]
    assert resultado.omitidos_sin_recepcion_reciente == 1


def test_varias_organizaciones_no_duplican_comandos():
    compartido = _disp("c1", "DDDDDDDDDD01")
    repo = _RepoDisp({"org-a": [compartido], "org-b": [compartido]})
    _, _, comando = _ejecutar(alcance_de_clientes([(False, "org-a"), (False, "org-b")]), repo=repo)
    assert comando.enviados == [("DDDDDDDDDD01", SEGUNDOS_TIEMPO_REAL)]


def test_alcance_vacio_no_consulta_ni_publica():
    resultado, repo, comando = _ejecutar(alcance_de_clientes([]))
    assert repo.llamadas == []
    assert comando.enviados == []
    assert resultado.renovados == 0


def test_comando_no_publicado_no_cuenta_como_renovado():
    resultado, _, comando = _ejecutar(alcance_de_clientes([(False, "org-b")]), comando=_Comando(resultado=False))
    assert len(comando.enviados) == 1
    assert resultado.renovados == 0
