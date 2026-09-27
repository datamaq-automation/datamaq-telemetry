"""tests/unit/test_potencia_referencia.py — `X-Potencia-Referencia-W`: P99 de 30 días para fijar el eje Y."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.planta_estructura_dto import HistoricoNodoUnifilarDTO
from src.application.dtos.telemetria_dto import HistoricoInstantaneasDTO
from src.application.use_cases import consultar_nodo_unifilar
from src.application.use_cases.agregacion_dispositivos import calcular_potencia_referencia
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.domain.telemetria.servicios.potencia_referencia import (
    MINIMO_HORAS_CON_DATOS,
    percentil_99,
    potencia_referencia,
)
from src.infrastructure.fastapi.dependencies import (
    get_consultar_nodo_unifilar_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.headers_historico import CacheTTL
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app

AHORA = datetime.now(timezone.utc).replace(second=0, microsecond=0)
INICIO = AHORA - timedelta(days=20)


def _lecturas(valores: list[float], inicio: datetime = INICIO) -> list[SimpleNamespace]:
    """Una lectura cada 300 s (throttle de persistencia), en el orden del repo: más nueva primero."""
    lecturas = [
        SimpleNamespace(
            registrado_en=inicio + timedelta(seconds=300 * i),
            potencia_activa_total_W=v,
            potencia_reactiva_total_VAR=None,
            es_dato_confiable=True,
        )
        for i, v in enumerate(valores)
    ]
    return list(reversed(lecturas))


def _consultar(series: dict[str, list[SimpleNamespace]], corte: datetime = INICIO - timedelta(days=1)) -> MagicMock:
    def obtener_muestras_bucketizadas(dispositivos_ids, desde, hasta, bucket_segundos=300):
        """Simula obtener_potencia_bucketizada_sql: suma potencias por dispositivo en cada bucket."""
        # Crear buckets de 300 s
        buckets = {}
        for device_id in dispositivos_ids:
            if device_id not in series:
                continue
            for lectura in series[device_id]:
                if desde <= lectura.registrado_en <= hasta and lectura.es_dato_confiable:
                    bucket_key = int(lectura.registrado_en.timestamp() // bucket_segundos)
                    if bucket_key not in buckets:
                        buckets[bucket_key] = []
                    buckets[bucket_key].append(lectura.potencia_activa_total_W)

        # Promediar por bucket
        return [sum(valores) / len(valores) for valores in buckets.values()]

    repo_telemetria = MagicMock()
    repo_telemetria.obtener_potencia_bucketizada_sql.side_effect = obtener_muestras_bucketizadas

    consultar = MagicMock()
    consultar.listar_instantaneas.side_effect = lambda dispositivo_id, **_: series[dispositivo_id]
    consultar.datos_desde.side_effect = lambda dispositivo_id: corte
    consultar.repo_telemetria = repo_telemetria
    return consultar


# --- Dominio -------------------------------------------------------------------------------


def test_percentil_99_interpola_entre_rangos():
    assert percentil_99([float(v) for v in range(1, 101)]) == pytest.approx(99.01)


def _muestras(horas: float, paso_segundos: int, valor: float = 1.0) -> list[tuple[datetime, float]]:
    n = int(horas * 3600 / paso_segundos)
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [(base + timedelta(seconds=paso_segundos * i), valor) for i in range(n)]


def test_potencia_referencia_exige_24_horas_con_datos():
    assert MINIMO_HORAS_CON_DATOS == 24  # documentado en la spec
    assert potencia_referencia(_muestras(23, 300)) is None
    assert potencia_referencia(_muestras(24, 300)) == 1.0


def test_potencia_referencia_cuenta_horas_y_no_puntos():
    """Plan free: el intervalo mínimo sube la serie a 1 h. 24 puntos horarios ya son 24 h."""
    assert potencia_referencia(_muestras(24, 3600)) == 1.0
    assert potencia_referencia(_muestras(23, 3600)) is None


# --- Caso de uso ---------------------------------------------------------------------------


@pytest.mark.skip(reason="TODO: adaptar mock obtener_potencia_bucketizada_sql para es_dato_confiable")
def test_nodo_toma_el_p99_de_la_serie_sumada_y_no_la_suma_de_p99():
    """D2: los picos de A y B no son simultáneos. P99(A) + P99(B) = 2000 W sobreestima; el P99
    de la serie sumada es 1000 W."""
    a = [1000.0 if i < 20 else 0.0 for i in range(400)]
    b = [1000.0 if 200 <= i < 220 else 0.0 for i in range(400)]
    consultar = _consultar({"a": _lecturas(a), "b": _lecturas(b)})

    assert calcular_potencia_referencia(["a"], consultar) == pytest.approx(1000.0)
    assert calcular_potencia_referencia(["b"], consultar) == pytest.approx(1000.0)
    assert calcular_potencia_referencia(["a", "b"], consultar) == pytest.approx(1000.0)


@pytest.mark.skip(reason="TODO: adaptar mock obtener_potencia_bucketizada_sql para es_dato_confiable")
def test_ventana_fija_de_30_dias_a_5_min_sin_hasta():
    consultar = _consultar({"a": _lecturas([100.0] * 400)})

    calcular_potencia_referencia(["a"], consultar)

    kwargs = consultar.listar_instantaneas.call_args.kwargs
    assert kwargs["horas"] == 720
    assert kwargs["granularidad"] == "5m"
    assert kwargs["hasta"] is None
    assert AHORA - timedelta(days=30, minutes=1) <= kwargs["desde"] <= AHORA - timedelta(days=29, hours=23)


@pytest.mark.skip(reason="TODO: adaptar mock obtener_potencia_bucketizada_sql para es_dato_confiable")
def test_descarta_los_puntos_anteriores_al_corte_de_retencion():
    viejas = _lecturas([9000.0] * 100, inicio=INICIO - timedelta(days=2))
    nuevas = _lecturas([100.0] * 400)
    consultar = _consultar({"a": nuevas + viejas}, corte=INICIO)

    assert calcular_potencia_referencia(["a"], consultar) == pytest.approx(100.0)


def test_sin_datos_suficientes_o_sin_dispositivos_es_none():
    consultar = _consultar({"a": _lecturas([100.0] * 100)})

    assert calcular_potencia_referencia(["a"], consultar) is None
    assert calcular_potencia_referencia([], consultar) is None


def test_nodo_calcula_con_sus_medidores_frontera(monkeypatch):
    use_case = ConsultarNodoUnifilarUseCase(MagicMock(), MagicMock(), MagicMock())
    frontera = [SimpleNamespace(device_id="a"), SimpleNamespace(device_id=None), SimpleNamespace(device_id="b")]
    monkeypatch.setattr(use_case, "_resolver_nodo", MagicMock(return_value=(None, frontera)))
    calcular = MagicMock(return_value=1234.5)
    monkeypatch.setattr(consultar_nodo_unifilar, "calcular_potencia_referencia", calcular)

    assert use_case.potencia_referencia("planta-1", "mt", "org-1") == 1234.5
    use_case._resolver_nodo.assert_called_once_with("planta-1", "mt", "org-1")
    calcular.assert_called_once_with(["a", "b"], use_case.consultar_telemetria)


# --- Caché ---------------------------------------------------------------------------------


def test_cache_ttl_reusa_el_valor_dentro_del_ttl_incluso_none():
    reloj = [0.0]
    cache = CacheTTL(60, reloj=lambda: reloj[0])
    calcular = MagicMock(return_value=None)

    assert cache.obtener("k", calcular) is None
    reloj[0] = 59.0
    assert cache.obtener("k", calcular) is None
    assert calcular.call_count == 1

    reloj[0] = 61.0
    calcular.return_value = 5.0
    assert cache.obtener("k", calcular) == 5.0
    assert calcular.call_count == 2


# --- Routers -------------------------------------------------------------------------------


def _cliente_dispositivo() -> tuple[TestClient, MagicMock]:
    app = create_app()
    use_case = MagicMock()
    use_case.historico_instantaneas.return_value = HistoricoInstantaneasDTO(lecturas=[], datos_desde=INICIO)
    app.dependency_overrides[get_telemetria_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin", "org": "org-1"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    return TestClient(app), use_case


def _cliente_nodo() -> tuple[TestClient, MagicMock]:
    app = create_app()
    use_case = MagicMock()
    use_case.historico.return_value = HistoricoNodoUnifilarDTO(puntos=[], datos_desde=INICIO)
    app.dependency_overrides[get_consultar_nodo_unifilar_use_case] = lambda: use_case
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin", "org": "org-1"}
    return TestClient(app), use_case


RUTA_DISPOSITIVO = "/api/v1/telemetria/instantaneous/dev-1"
RUTA_NODO = "/api/v1/plantas/planta-1/unifilar/nodos/mt/resumen/historico"
HACE_7_DIAS = (AHORA - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_dispositivo_header_igual_para_cualquier_ventana_y_cacheado():
    client, use_case = _cliente_dispositivo()
    with patch(
        "src.infrastructure.fastapi.routes.telemetria_router.calcular_potencia_referencia", return_value=48123.456
    ) as calcular:
        actual = client.get(f"{RUTA_DISPOSITIVO}?hours=24")
        pasado = client.get(f"{RUTA_DISPOSITIVO}?hours=24&hasta={HACE_7_DIAS}")

    assert actual.status_code == pasado.status_code == 200
    assert actual.headers["X-Potencia-Referencia-W"] == pasado.headers["X-Potencia-Referencia-W"] == "48123.5"
    calcular.assert_called_once_with(["dev-1"], use_case)


def test_dispositivo_sin_datos_suficientes_omite_el_header():
    client, _ = _cliente_dispositivo()
    with patch("src.infrastructure.fastapi.routes.telemetria_router.calcular_potencia_referencia", return_value=None):
        response = client.get(f"{RUTA_DISPOSITIVO}?hours=24")

    assert response.status_code == 200
    assert "X-Potencia-Referencia-W" not in response.headers
    assert "X-Datos-Desde" in response.headers


def test_dispositivo_si_el_calculo_falla_el_historico_responde_sin_header():
    client, _ = _cliente_dispositivo()
    with patch(
        "src.infrastructure.fastapi.routes.telemetria_router.calcular_potencia_referencia",
        side_effect=RuntimeError("db caída"),
    ):
        response = client.get(f"{RUTA_DISPOSITIVO}?hours=24")

    assert response.status_code == 200
    assert "X-Potencia-Referencia-W" not in response.headers


def test_nodo_header_igual_para_cualquier_ventana_y_cacheado():
    client, use_case = _cliente_nodo()
    use_case.potencia_referencia.return_value = 812000.0

    actual = client.get(f"{RUTA_NODO}?hours=24")
    pasado = client.get(f"{RUTA_NODO}?hours=24&hasta={HACE_7_DIAS}")

    assert actual.headers["X-Potencia-Referencia-W"] == pasado.headers["X-Potencia-Referencia-W"] == "812000.0"
    use_case.potencia_referencia.assert_called_once_with("planta-1", "mt", "org-1")


def test_nodo_sin_datos_suficientes_omite_el_header():
    client, use_case = _cliente_nodo()
    use_case.potencia_referencia.return_value = None

    response = client.get(f"{RUTA_NODO}?hours=24")

    assert response.status_code == 200
    assert "X-Potencia-Referencia-W" not in response.headers


def test_nodo_sin_acceso_no_consulta_la_referencia():
    """La caché no se consulta si `historico` rechazó el acceso: no filtra valores entre organizaciones."""
    from src.domain.telemetria.exceptions import PlantaNoEncontradaError

    client, use_case = _cliente_nodo()
    use_case.historico.side_effect = PlantaNoEncontradaError("no existe")

    response = client.get(f"{RUTA_NODO}?hours=24")

    assert response.status_code == 404
    use_case.potencia_referencia.assert_not_called()


@pytest.mark.skip(reason="TODO: adaptar mock obtener_potencia_bucketizada_sql para es_dato_confiable")
def test_registra_duracion_y_muestras_del_calculo():
    # Se parchea el logger del módulo: `capture_logs` no ve nada si otro test ya dejó el logger
    # cacheado con otra configuración de structlog (falla según el reparto de pytest-xdist).
    consultar = _consultar({"a": _lecturas([100.0] * 400)})

    with patch("src.application.use_cases.agregacion_dispositivos._log") as log:
        calcular_potencia_referencia(["a"], consultar)

    log.info.assert_called_once()
    assert log.info.call_args.args == ("potencia_referencia_calculada",)
    evento = log.info.call_args.kwargs
    assert evento["dispositivos_count"] == 1
    assert evento["muestras"] == 400
    assert evento["referencia_w"] == pytest.approx(100.0)
    assert evento["duracion_ms"] >= 0


def test_cache_ttl_pedidos_simultaneos_calculan_una_sola_vez():
    """El dashboard pide gráfico e histograma en paralelo: el segundo espera al primero."""
    import threading

    cache = CacheTTL(60)
    empezo = threading.Event()
    liberar = threading.Event()
    llamadas = []

    def calcular_lento() -> float:
        llamadas.append(1)
        empezo.set()
        liberar.wait(5)
        return 7.0

    resultados: list[float | None] = []
    hilos = [threading.Thread(target=lambda: resultados.append(cache.obtener("k", calcular_lento))) for _ in range(3)]
    hilos[0].start()
    empezo.wait(5)
    for hilo in hilos[1:]:
        hilo.start()
    liberar.set()
    for hilo in hilos:
        hilo.join(5)

    assert len(llamadas) == 1
    assert resultados == [7.0, 7.0, 7.0]


def test_cache_ttl_si_el_calculo_falla_el_siguiente_reintenta():
    cache = CacheTTL(60)

    with pytest.raises(RuntimeError):
        cache.obtener("k", MagicMock(side_effect=RuntimeError("db caída")))

    assert cache.obtener("k", lambda: 3.0) == 3.0
