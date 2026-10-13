"""tools/mcp/test_calidad_integracion.py — Compuerta de calidad en las tools del MCP (#31).

Cliente HTTP mockeado con MockTransport: ninguna llamada sale de la prueba ni toca la base real.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from tools.mcp.server import (
    datamaq_analizar_capacitores,
    datamaq_consultar_penalizaciones,
    datamaq_consultar_potencia_reciente,
    set_client,
)


@pytest.fixture(autouse=True)
def limpiar_cliente():
    yield
    set_client(None)


def _serie(potencia_w: float, buckets: int = 288) -> list[dict[str, Any]]:
    """Lecturas consecutivas de 5 min desde 2026-10-06 00:00 UTC (288 = un día completo)."""
    inicio = datetime(2026, 10, 6, tzinfo=timezone.utc)
    return [
        {
            "registrado_en": (inicio + timedelta(minutes=5 * i)).isoformat().replace("+00:00", "Z"),
            "potencia_activa_total_W": potencia_w,
            "potencia_reactiva_total_VAR": 5_000.0,
        }
        for i in range(buckets)
    ]


def _dispositivo(id_: str, fases: str = "R,S,T", tipo: str = "CONSUMO") -> dict[str, Any]:
    return {"id": id_, "ubicacion_tag": f"Tag {id_}", "tipo_instalacion": tipo, "fases_con_ti": fases}


def _cliente(
    dispositivos: list[dict[str, Any]] | None,
    lecturas: dict[str, list[dict[str, Any]]],
    alertas: list[dict[str, Any]] | None = None,
    backend: dict[str, Any] | None = None,
    llamadas: list[str] | None = None,
    dispositivos_status: int = 200,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        ruta = request.url.path
        if llamadas is not None:
            llamadas.append(ruta)
        if ruta == "/api/v1/dispositivos":
            if dispositivos_status != 200:
                return httpx.Response(dispositivos_status, json={"detail": "error"})
            return httpx.Response(200, json=dispositivos or [])
        if ruta == "/api/v1/alertas":
            return httpx.Response(200, json=alertas or [])
        if ruta.startswith("/api/v1/telemetria/instantaneous/"):
            dispositivo_id = ruta.rsplit("/", 1)[-1]
            return httpx.Response(200, json=lecturas.get(dispositivo_id, []))
        if ruta.startswith("/api/v1/analitica/"):
            return httpx.Response(200, json=backend or {"kvar_recomendados": 120.0})
        return httpx.Response(404, json={"detail": "no mock"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://datamaq.local")


@pytest.mark.asyncio
async def test_analizar_capacitores_bloquea_con_p_negativa_sostenida() -> None:
    """Patrón del 369: P negativa en todos los buckets de un medidor de consumo. No se entrega kVAr."""
    llamadas: list[str] = []
    set_client(
        _cliente(
            dispositivos=[_dispositivo("dev-369")],
            lecturas={"dev-369": _serie(-33_000.0)},
            llamadas=llamadas,
        )
    )

    resultado = await datamaq_analizar_capacitores("planta-san-martin", periodo_dias=1)

    assert resultado["estado"] == "bloqueado_por_calidad_de_datos"
    assert [m["dispositivo_id"] for m in resultado["medidores"]] == ["dev-369"]
    assert "S2" in resultado["medidores"][0]["codigos"]
    assert "kvar_recomendados" not in resultado
    assert "/api/v1/analitica/banco-capacitores/planta" not in llamadas


@pytest.mark.asyncio
async def test_analizar_capacitores_bloquea_con_alerta_de_polaridad_abierta() -> None:
    set_client(
        _cliente(
            dispositivos=[_dispositivo("dev-1")],
            lecturas={"dev-1": _serie(30_000.0)},
            alertas=[{"dispositivo_id": "dev-1", "tipo_alerta": "POLARIDAD_TI", "categoria": "POLARIDAD_TI"}],
        )
    )

    resultado = await datamaq_analizar_capacitores("planta-x", periodo_dias=1)

    assert resultado["estado"] == "bloqueado_por_calidad_de_datos"


@pytest.mark.asyncio
async def test_analizar_capacitores_con_fase_faltante_entrega_el_calculo_con_advertencia() -> None:
    """S4 no bloquea: el kVAr sale, y el bloque calidad_datos dice qué fase falta."""
    set_client(
        _cliente(
            dispositivos=[_dispositivo("dev-2", fases="R,S")],
            lecturas={"dev-2": _serie(30_000.0)},
        )
    )

    resultado = await datamaq_analizar_capacitores("planta-x", periodo_dias=1)

    assert resultado["kvar_recomendados"] == 120.0
    assert resultado["calidad_datos"]["verificada"] is True
    assert resultado["calidad_datos"]["total_trifasico_completo"] is False
    assert resultado["calidad_datos"]["dispositivos_no_trifasicos"] == [
        {"dispositivo_id": "dev-2", "fases_faltantes": ["T"]}
    ]


@pytest.mark.asyncio
async def test_penalizaciones_bloquea_con_p_negativa() -> None:
    set_client(_cliente(dispositivos=[_dispositivo("dev-369")], lecturas={"dev-369": _serie(-33_000.0)}))

    resultado = await datamaq_consultar_penalizaciones("planta-san-martin", periodo_dias=1)

    assert resultado["estado"] == "bloqueado_por_calidad_de_datos"


@pytest.mark.asyncio
async def test_potencia_reciente_nunca_bloquea_y_marca_el_medidor_sospechoso() -> None:
    set_client(
        _cliente(
            dispositivos=[_dispositivo("dev-369"), _dispositivo("dev-ok")],
            lecturas={"dev-369": _serie(-33_000.0), "dev-ok": _serie(30_000.0)},
        )
    )

    resultado = await datamaq_consultar_potencia_reciente("planta-san-martin", horas=24)

    assert "estado" not in resultado
    assert resultado["potencia_activa_promedio_kw"] is not None
    sospechosos = resultado["calidad_datos"]["medidores_sospechosos"]
    assert [m["dispositivo_id"] for m in sospechosos] == ["dev-369"]


@pytest.mark.asyncio
async def test_sin_listado_de_medidores_no_bloquea_y_lo_declara() -> None:
    """Si no se pueden listar medidores, la compuerta no puede verificar: el cálculo sale con la marca."""
    set_client(_cliente(dispositivos=None, lecturas={}, dispositivos_status=500))

    resultado = await datamaq_analizar_capacitores("planta-x", periodo_dias=1)

    assert resultado["kvar_recomendados"] == 120.0
    assert resultado["calidad_datos"]["verificada"] is False
