"""tests/unit/test_alertas_dedup_ingesta.py — La ingesta actualiza la alerta abierta en vez de abrir otra (#19).

Antes, cada detección que pasaba el filtro de persistencia abría una alerta nueva: un medidor de Durax acumuló
116 SOBRECOMPENSACION_REACTIVA abiertas a la vez.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.use_cases.ingesta.procesador_alertas_ingesta import _despachar_alerta_fn
from src.domain.telemetria.entities import AlertaDispositivo
from src.domain.telemetria.value_objects import SeveridadAlerta

T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


class _RepoAlertas:
    def __init__(self) -> None:
        self.alertas: dict[int, AlertaDispositivo] = {}
        self._siguiente = 1

    def listar_alertas(self, dispositivo_id: str | None = None, solo_abiertas: bool = False, **_: Any):
        return [
            a
            for a in self.alertas.values()
            if (dispositivo_id is None or a.dispositivo_id == dispositivo_id)
            and not (solo_abiertas and a.esta_resuelta)
        ]

    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        if alerta.id is None:
            alerta.id = self._siguiente
            self._siguiente += 1
        self.alertas[alerta.id] = alerta

    def abiertas(self) -> list[AlertaDispositivo]:
        return [a for a in self.alertas.values() if not a.esta_resuelta]


class _Publicador:
    def __init__(self) -> None:
        self.eventos: list[dict[str, Any]] = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        self.eventos.append(datos)


def _deteccion(minutos: int, tipo: str = "SOBRECOMPENSACION_REACTIVA", fase: str | None = None, q: float = -10.0):
    return AlertaDispositivo(
        id=None,
        dispositivo_id="bf2c",
        tipo_alerta=tipo,
        severidad=SeveridadAlerta.WARNING,
        mensaje=f"Q={q} kvar",
        disparada_en=T0 + timedelta(minutes=minutos),
        fase=fase,
        valor_medido=q,
    )


def test_detecciones_repetidas_de_la_misma_condicion_dejan_una_sola_abierta():
    repo = _RepoAlertas()
    for i in range(116):
        _despachar_alerta_fn(_deteccion(i * 5, q=-10.0 - i), "BF2C", repo, None, None)

    abiertas = repo.abiertas()
    assert len(abiertas) == 1
    assert abiertas[0].ocurrencias == 116
    assert abiertas[0].disparada_en == T0
    assert abiertas[0].ultima_deteccion_en == T0 + timedelta(minutes=115 * 5)
    assert abiertas[0].valor_medido == -125.0


def test_otro_tipo_u_otra_fase_abren_su_propia_alerta():
    repo = _RepoAlertas()
    _despachar_alerta_fn(_deteccion(0), "BF2C", repo, None, None)
    _despachar_alerta_fn(_deteccion(5, tipo="BAJA_TENSION", fase="R"), "BF2C", repo, None, None)
    _despachar_alerta_fn(_deteccion(10, tipo="BAJA_TENSION", fase="S"), "BF2C", repo, None, None)
    _despachar_alerta_fn(_deteccion(15, tipo="BAJA_TENSION", fase="R"), "BF2C", repo, None, None)

    assert len(repo.abiertas()) == 3


def test_despues_de_resolverse_una_nueva_deteccion_abre_otra_alerta():
    repo = _RepoAlertas()
    _despachar_alerta_fn(_deteccion(0), "BF2C", repo, None, None)
    repo.abiertas()[0].marcar_resuelta(T0 + timedelta(minutes=30))
    _despachar_alerta_fn(_deteccion(60), "BF2C", repo, None, None)

    assert len(repo.alertas) == 2
    assert len(repo.abiertas()) == 1
    assert repo.abiertas()[0].ocurrencias == 1


def test_con_duplicadas_previas_actualiza_la_mas_antigua():
    repo = _RepoAlertas()
    vieja = _deteccion(0)
    nueva = _deteccion(60)
    repo.guardar_alerta(nueva)
    repo.guardar_alerta(vieja)

    _despachar_alerta_fn(_deteccion(120), "BF2C", repo, None, None)

    assert vieja.ocurrencias == 2
    assert nueva.ocurrencias == 1


def test_la_reincidencia_se_publica_en_vivo_con_las_ocurrencias():
    repo = _RepoAlertas()
    pub = _Publicador()
    _despachar_alerta_fn(_deteccion(0), "BF2C", repo, pub, None)
    _despachar_alerta_fn(_deteccion(5), "BF2C", repo, pub, None)

    assert [e["ocurrencias"] for e in pub.eventos] == [1, 2]
    assert pub.eventos[0]["id"] == pub.eventos[1]["id"]
