"""tests/unit/test_navegacion_temporal.py — `hasta` y `datos_desde` en los históricos de potencia.

Spec: `specs/navegacion-temporal-telemetria.md`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.agregacion_dispositivos import calcular_datos_desde, calcular_historico
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase, NodoUnifilar, Planta
from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva, TipoNodoUnifilar

DEV_ID = "dev-nav"


def _lectura(momento: datetime, vatios: float = 1000.0, dispositivo_id: str = DEV_ID) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=momento,
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios),
    )


class FakeRepoTelemetria:
    """Imita el contrato SQL: filtra [desde, hasta], ordena de más nueva a más vieja y aplica el límite."""

    def __init__(self, lecturas: list[LecturaInstantanea]):
        self.lecturas = lecturas
        self.llamadas: list[dict] = []

    def listar_instantaneas(self, dispositivo_id, limite, desde=None, hasta=None):
        self.llamadas.append({"limite": limite, "desde": desde, "hasta": hasta})
        items = [
            lectura
            for lectura in self.lecturas
            if lectura.dispositivo_id == dispositivo_id
            and (desde is None or lectura.registrado_en >= desde)
            and (hasta is None or lectura.registrado_en <= hasta)
        ]
        items.sort(key=lambda lectura: lectura.registrado_en, reverse=True)
        return items[:limite]


class FakeBuffer:
    def __init__(self, momentos: list[datetime]):
        self._datos = [
            {
                "dispositivo_id": DEV_ID,
                "registrado_en": m.isoformat(),
                "fase_r": {},
                "fase_s": {},
                "fase_t": {},
                "potencia_activa_total_W": 1.0,
            }
            for m in momentos
        ]

    def obtener(self, dispositivo_id: str) -> list[dict]:
        return self._datos


def _use_case(lecturas: list[LecturaInstantanea], buffer: FakeBuffer | None = None):
    repo_disp = MagicMock()
    repo_disp.obtener_por_id.return_value = Dispositivo(
        id=DEV_ID, device_uid=MacAddress("D48C49F03564"), nombre="Medidor nav"
    )
    repo = FakeRepoTelemetria(lecturas)
    # Sin repo de organizaciones el dispositivo no tiene suscripción: corte de retención = now - 14 d.
    return ConsultarTelemetriaUseCase(repo, repo_disp, buffer_en_vivo=buffer), repo


def _piso_5min(momento: datetime) -> datetime:
    return momento.replace(minute=momento.minute - momento.minute % 5, second=0, microsecond=0)


# --- Dispositivo ---------------------------------------------------------------------------------


def test_hasta_acota_la_ventana_por_arriba():
    t0 = _piso_5min(datetime.now(timezone.utc) - timedelta(days=2))
    uc, repo = _use_case([_lectura(t0), _lectura(t0 + timedelta(hours=1)), _lectura(t0 + timedelta(hours=2))])

    res = uc.listar_instantaneas(DEV_ID, limite=100, desde=t0, granularidad="raw", hasta=t0 + timedelta(hours=1))

    assert [r.registrado_en for r in res] == [t0 + timedelta(hours=1), t0]
    assert repo.llamadas[-1]["hasta"] == t0 + timedelta(hours=1)


def test_ventana_entera_antes_del_corte_es_vacia_sin_consultar_la_bd():
    hasta = datetime.now(timezone.utc) - timedelta(days=20)
    uc, repo = _use_case([_lectura(hasta - timedelta(minutes=30))])

    res = uc.listar_instantaneas(DEV_ID, limite=100, desde=hasta - timedelta(hours=1), horas=1, hasta=hasta)

    assert res == []
    assert repo.llamadas == []


def test_buffer_en_vivo_no_se_mezcla_en_una_ventana_del_pasado():
    ahora = datetime.now(timezone.utc)
    hasta = ahora - timedelta(hours=2)
    uc, _ = _use_case([_lectura(hasta - timedelta(minutes=10))], FakeBuffer([ahora - timedelta(seconds=5)]))

    res = uc.listar_instantaneas(DEV_ID, limite=100, desde=hasta - timedelta(hours=1), granularidad="raw", hasta=hasta)

    assert [r.registrado_en for r in res] == [hasta - timedelta(minutes=10)]


def test_buffer_en_vivo_se_mezcla_en_el_ultimo_intervalo_sin_lecturas_posteriores_a_hasta():
    ahora = datetime.now(timezone.utc).replace(microsecond=0)
    hasta = ahora - timedelta(seconds=30)
    buffer = FakeBuffer([ahora - timedelta(seconds=60), ahora - timedelta(seconds=10)])
    uc, _ = _use_case([], buffer)

    res = uc.listar_instantaneas(DEV_ID, limite=100, desde=hasta - timedelta(hours=1), granularidad="raw", hasta=hasta)

    assert [r.registrado_en for r in res] == [ahora - timedelta(seconds=60)]


def test_sin_hasta_el_buffer_se_sigue_mezclando():
    ahora = datetime.now(timezone.utc).replace(microsecond=0)
    uc, _ = _use_case([], FakeBuffer([ahora - timedelta(seconds=10)]))

    res = uc.listar_instantaneas(DEV_ID, limite=100, desde=ahora - timedelta(hours=1), granularidad="raw")

    assert [r.registrado_en for r in res] == [ahora - timedelta(seconds=10)]


def test_historico_instantaneas_informa_el_corte_de_retencion():
    uc, _ = _use_case([])
    antes = datetime.now(timezone.utc) - timedelta(days=14)

    historico = uc.historico_instantaneas(DEV_ID, limite=10, granularidad="raw")

    despues = datetime.now(timezone.utc) - timedelta(days=14)
    assert historico.lecturas == []
    assert antes <= historico.datos_desde <= despues


# --- Agregación de varios dispositivos ------------------------------------------------------------


def test_calcular_historico_dimensiona_el_limite_y_pasa_la_ventana():
    consultar = MagicMock()
    consultar.lecturas_crudas.listar.return_value = []
    consultar.lecturas_crudas.intervalo_minimo_segundos.return_value = 0
    hasta = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)

    calcular_historico(["a", "b"], consultar, "5m", 168, hasta)

    for llamada in consultar.lecturas_crudas.listar.call_args_list:
        assert llamada.kwargs["limite"] >= 2017
        assert llamada.kwargs["desde"] == hasta - timedelta(hours=168)
        assert llamada.kwargs["hasta"] == hasta


def test_semana_a_5_minutos_llega_completa():
    """Regresión: con limite=2000 fijo se perdían los ~80 min más viejos de la semana."""
    hasta = _piso_5min(datetime.now(timezone.utc) - timedelta(hours=1))
    inicio = hasta - timedelta(hours=168)
    lecturas = [_lectura(inicio + timedelta(seconds=300 * i)) for i in range(2017)]
    uc, _ = _use_case(lecturas)

    puntos = calcular_historico([DEV_ID], uc, "5m", 168, hasta)

    assert len(puntos) == 2017
    assert min(p.momento for p in puntos) == inicio


def test_calcular_datos_desde_toma_el_corte_mas_reciente():
    consultar = MagicMock()
    c1 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    c2 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    consultar.datos_desde.side_effect = {"a": c1, "b": c2}.get

    assert calcular_datos_desde(["a", "b"], consultar) == c2
    assert calcular_datos_desde([], consultar) is None


# --- Nodo del unifilar ----------------------------------------------------------------------------


@pytest.fixture
def nodo_use_case():
    repo_org = MagicMock()
    repo_org.obtener_planta_por_id.return_value = Planta(id="p", organizacion_id="o", nombre="P")
    repo_org.obtener_nodos_unifilar.return_value = [
        NodoUnifilar(id="mt", planta_id="p", nombre="mt", tipo=TipoNodoUnifilar.ACOMETIDA, tension_nominal_v=380.0),
        NodoUnifilar(
            id="t1",
            planta_id="p",
            nombre="t1",
            tipo=TipoNodoUnifilar.TRANSFORMADOR,
            tension_nominal_v=380.0,
            parent_id="mt",
            device_id="a",
        ),
        NodoUnifilar(
            id="t2",
            planta_id="p",
            nombre="t2",
            tipo=TipoNodoUnifilar.TRANSFORMADOR,
            tension_nominal_v=380.0,
            parent_id="mt",
            device_id="b",
        ),
        NodoUnifilar(
            id="vacio",
            planta_id="p",
            nombre="vacio",
            tipo=TipoNodoUnifilar.SECCIONAL,
            tension_nominal_v=380.0,
            parent_id="mt",
        ),
    ]
    return ConsultarNodoUnifilarUseCase(repo_org, MagicMock(), MagicMock())


def _lectura_dto(dispositivo_id: str, momento: datetime):
    dto = MagicMock()
    dto.registrado_en = momento
    dto.potencia_activa_total_W = 100.0
    dto.potencia_reactiva_total_VAR = None
    return dto


def test_nodo_filtra_puntos_anteriores_al_corte_mas_reciente(nodo_use_case):
    c1 = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    c2 = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)
    consultar = nodo_use_case.consultar_telemetria
    consultar.datos_desde.side_effect = {"a": c1, "b": c2}.get
    # "a" tiene datos desde c1; "b" recién desde c2: antes de c2 la suma estaría incompleta.
    consultar.listar_instantaneas.side_effect = lambda dev, **kw: [
        _lectura_dto(dev, c2 + timedelta(minutes=5)),
        _lectura_dto(dev, c1 + timedelta(minutes=5)),
    ]
    consultar.lecturas_crudas.intervalo_minimo_segundos.return_value = 0
    consultar.lecturas_crudas.listar.side_effect = lambda dev, **kw: [
        (d.registrado_en, d.potencia_activa_total_W, d.potencia_reactiva_total_VAR)
        for d in consultar.listar_instantaneas(dev, **kw)
    ]

    historico = nodo_use_case.historico("p", "mt", "o", "5m", 24, hasta=c2 + timedelta(hours=1))

    assert historico.datos_desde == c2
    assert [p.momento for p in historico.puntos] == [c2 + timedelta(minutes=5)]
    assert consultar.listar_instantaneas.call_args.kwargs["hasta"] == c2 + timedelta(hours=1)


def test_nodo_sin_medidores_frontera_no_informa_datos_desde(nodo_use_case):
    historico = nodo_use_case.historico("p", "vacio", "o", "5m", 24)

    assert historico.datos_desde is None
    assert historico.puntos == []
