"""tools/mcp/server.py — Servidor MCP (Model Context Protocol) para DataMaq.

Expone herramientas de diagnóstico y analítica energética para Claude Desktop y Claude Code
utilizando FastMCP sobre transporte stdio y cliente HTTP httpx.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP(
    "datamaq-mcp",
    instructions=(
        "Servidor MCP de telemetría y diagnóstico energético industrial de DataMaq. "
        "Permite consultar plantas, alertas, analítica de compensación reactiva "
        "(banco de capacitores), penalizaciones por bajo cos phi y curvas de potencia."
    ),
)
mcp.settings.transport_security = None
mcp.settings.streamable_http_path = "/"

_custom_client: httpx.AsyncClient | None = None


def set_client(client: httpx.AsyncClient | None) -> None:
    """Inyecta un cliente httpx personalizado (utilizado en pruebas con MockTransport)."""
    global _custom_client
    _custom_client = client


def _obtener_configuracion() -> tuple[str, str | None]:
    """Obtiene la URL base y el token JWT de las variables de entorno."""
    es_produccion = (
        os.getenv("APP_ENV") == "production"
        or os.getenv("ENVIRONMENT") == "production"
        or os.path.exists("/var/www/datamaq-telemetry")
    )
    default_url = "http://127.0.0.1:8885" if es_produccion else "http://localhost:8000"
    api_url = os.getenv("DATAMAQ_API_URL", default_url).rstrip("/")
    auth_token = os.getenv("DATAMAQ_AUTH_TOKEN")
    return api_url, auth_token


def _resolver_token(ctx: Context | None = None) -> str | None:
    """Resuelve el token Bearer en orden de prioridad:
    1. Header Authorization entrante vía MCP Context (clientes HTTP / OAuth como Claude.ai).
    2. Variable de entorno DATAMAQ_AUTH_TOKEN (modo CLI stdio).
    3. Si no existe ninguno y no hay _custom_client inyectado para tests, emite excepción 401.
    """
    if ctx is not None:
        try:
            req_ctx = getattr(ctx, "request_context", None)
            if req_ctx is not None:
                request = getattr(req_ctx, "request", None)
                if request is not None and hasattr(request, "headers") and request.headers is not None:
                    auth_header = request.headers.get("authorization")
                    if auth_header:
                        if auth_header.lower().startswith("bearer "):
                            return auth_header[7:].strip()
                        return auth_header.strip()
        except Exception:
            pass

    token_env = os.getenv("DATAMAQ_AUTH_TOKEN")
    if token_env and token_env.strip():
        return token_env.strip()

    if _custom_client is not None:
        return None

    raise RuntimeError(
        "Error 401 (No autorizado): No se suministró token de autenticación (vía header Bearer o DATAMAQ_AUTH_TOKEN)."
    )


@asynccontextmanager
async def _obtener_cliente_http() -> AsyncIterator[httpx.AsyncClient]:
    """Context manager que provee un AsyncClient para interactuar con DataMaq API."""
    if _custom_client is not None:
        yield _custom_client
        return

    api_url, _ = _obtener_configuracion()
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "DataMaq-MCP-Server/1.0",
    }
    async with httpx.AsyncClient(base_url=api_url, headers=headers, timeout=30.0) as client:
        yield client


async def _ejecutar_peticion(
    metodo: str,
    ruta: str,
    token: str | None = None,
    **kwargs: Any,
) -> Any:
    """Ejecuta una petición HTTP contra la API de DataMaq gestionando errores."""
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with _obtener_cliente_http() as client:
        try:
            response = await client.request(metodo, ruta, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            codigo = exc.response.status_code
            try:
                detalle = exc.response.json().get("detail", exc.response.text)
            except Exception:
                detalle = exc.response.text

            if codigo == 401:
                mensaje = (
                    "Error 401 (No autorizado): Verifique que DATAMAQ_AUTH_TOKEN "
                    f"sea válido y esté configurado. Detalle: {detalle}"
                )
            elif codigo == 403:
                mensaje = (
                    f"Error 403 (Acceso denegado): No posee permisos suficientes para acceder a {ruta}. "
                    f"Detalle: {detalle}"
                )
            elif codigo == 404:
                mensaje = f"Error 404 (No encontrado): El recurso solicitado en {ruta} no existe. Detalle: {detalle}"
            else:
                mensaje = f"Error HTTP {codigo} al consultar {ruta}: {detalle}"

            raise RuntimeError(mensaje) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Error de conexión con DataMaq API ({ruta}): {exc}") from exc


@mcp.tool()
async def datamaq_listar_plantas(ctx: Context | None = None) -> list[dict[str, Any]]:
    """Retorna las plantas industriales a las que el usuario autenticado tiene acceso en DataMaq."""
    token = _resolver_token(ctx)
    resultado = await _ejecutar_peticion("GET", "/api/v1/plantas", token=token)
    if isinstance(resultado, list):
        return resultado
    return [resultado]


@mcp.tool()
async def datamaq_consultar_alertas(
    planta_id: str,
    solo_abiertas: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Lista las alertas eléctricas y operativas recientes para la planta especificada.

    Args:
        planta_id: Identificador de la planta industrial.
        solo_abiertas: Si es True, solo retorna alertas no resueltas.
        ctx: Contexto de ejecución FastMCP inyectado automáticamente.
    """
    token = _resolver_token(ctx)
    dispositivos_resp = await _ejecutar_peticion(
        "GET", "/api/v1/dispositivos", token=token, params={"planta_id": planta_id}
    )
    dispositivos_map: dict[str, str] = {}
    if isinstance(dispositivos_resp, list):
        for d in dispositivos_resp:
            if isinstance(d, dict) and d.get("id"):
                dispositivos_map[d["id"]] = d.get("ubicacion_tag") or d.get("nombre") or d["id"]

    parametros: dict[str, Any] = {
        "planta_id": planta_id,
        "solo_abiertas": solo_abiertas,
    }
    resultado = await _ejecutar_peticion("GET", "/api/v1/alertas", token=token, params=parametros)
    alertas_raw = resultado if isinstance(resultado, list) else [resultado]

    alertas_filtradas: list[dict[str, Any]] = []
    for a in alertas_raw:
        if not isinstance(a, dict):
            continue
        dev_id = a.get("dispositivo_id")
        if dev_id and dev_id in dispositivos_map:
            alerta_enriquecida = dict(a)
            alerta_enriquecida["planta_id"] = planta_id
            alerta_enriquecida["dispositivo_tag"] = dispositivos_map[dev_id]
            alertas_filtradas.append(alerta_enriquecida)

    return alertas_filtradas


@mcp.tool()
async def datamaq_analizar_capacitores(
    planta_id: str,
    periodo_dias: int = 30,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Ejecuta la analítica SSOT de banco de capacitores y recomendación de compensación en kVAr.

    Args:
        planta_id: Identificador único de la planta industrial.
        periodo_dias: Ventana de análisis en días (por defecto 30, mínimo según ISO 50001).
        ctx: Contexto de ejecución FastMCP inyectado automáticamente.
    """
    token = _resolver_token(ctx)
    parametros: dict[str, Any] = {
        "planta_id": planta_id,
        "periodo_dias": periodo_dias,
    }
    resultado = await _ejecutar_peticion(
        "GET", "/api/v1/analitica/banco-capacitores/planta", token=token, params=parametros
    )
    if isinstance(resultado, dict):
        return resultado
    return {"resultado": resultado}


@mcp.tool()
async def datamaq_consultar_penalizaciones(
    planta_id: str,
    periodo_dias: int = 7,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Obtiene el acumulado estimado de recargos y multas por bajo factor de potencia (cos phi).

    Args:
        planta_id: Identificador único de la planta industrial.
        periodo_dias: Ventana de análisis en días (por defecto 7).
        ctx: Contexto de ejecución FastMCP inyectado automáticamente.
    """
    token = _resolver_token(ctx)
    parametros: dict[str, Any] = {
        "planta_id": planta_id,
        "periodo_dias": periodo_dias,
    }
    resultado = await _ejecutar_peticion(
        "GET", "/api/v1/analitica/penalizaciones/planta", token=token, params=parametros
    )
    if isinstance(resultado, dict):
        return resultado
    return {"resultado": resultado}


_BUCKET_SEGUNDOS = 300  # Serie de planta en buckets de 5 min (misma granularidad que el backend)


def _agregar_serie_planta(lecturas_por_dispositivo: list[list[dict[str, Any]]]) -> list[dict[str, float | None]]:
    """Suma P y Q de todos los dispositivos por bucket de 5 min; FP es el promedio de los puntos."""
    buckets: dict[int, dict[str, Any]] = {}
    for lecturas in lecturas_por_dispositivo:
        for lectura in lecturas:
            marca = lectura.get("registrado_en")
            if not isinstance(marca, str):
                continue
            instante = datetime.fromisoformat(marca.replace("Z", "+00:00"))
            clave = int(instante.timestamp()) // _BUCKET_SEGUNDOS
            bucket = buckets.setdefault(clave, {"p_w": None, "q_var": None, "fps": []})
            p_w = lectura.get("potencia_activa_total_W")
            q_var = lectura.get("potencia_reactiva_total_VAR")
            if p_w is not None:
                bucket["p_w"] = (bucket["p_w"] or 0.0) + float(p_w)
            if q_var is not None:
                bucket["q_var"] = (bucket["q_var"] or 0.0) + float(q_var)
            if lectura.get("factor_potencia_total") is not None:
                bucket["fps"].append(float(lectura["factor_potencia_total"]))
    return [
        {
            "p_kw": b["p_w"] / 1000.0 if b["p_w"] is not None else None,
            "q_kvar": b["q_var"] / 1000.0 if b["q_var"] is not None else None,
            "fp": sum(b["fps"]) / len(b["fps"]) if b["fps"] else None,
        }
        for _, b in sorted(buckets.items())
    ]


def _promedio(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


@mcp.tool()
async def datamaq_consultar_potencia_reciente(
    planta_id: str,
    horas: int = 24,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Consulta el resumen de demanda activa (kW) y reactiva (kVAr) de una planta en una ventana de horas reciente.

    Recorre los dispositivos de la planta y consulta la serie instantánea de cada uno; la planta se
    arma sumando P y Q por bucket de 5 min. Los dispositivos que fallan se listan en
    `dispositivos_con_error` sin cortar la consulta.

    Args:
        planta_id: Identificador único de la planta industrial.
        horas: Cantidad de horas recientes a consultar (por defecto 24, máximo 720).
        ctx: Contexto de ejecución FastMCP inyectado automáticamente.
    """
    token = _resolver_token(ctx)
    dispositivos = await _ejecutar_peticion("GET", "/api/v1/dispositivos", token=token, params={"planta_id": planta_id})
    ids = (
        [d["id"] for d in dispositivos if isinstance(d, dict) and d.get("id")] if isinstance(dispositivos, list) else []
    )

    lecturas_por_dispositivo: list[list[dict[str, Any]]] = []
    con_error: list[str] = []
    for dispositivo_id in ids:
        try:
            lecturas = await _ejecutar_peticion(
                "GET",
                f"/api/v1/telemetria/instantaneous/{dispositivo_id}",
                token=token,
                params={"hours": horas, "granularity": "5m", "limit": 5000},
            )
        except RuntimeError:
            con_error.append(dispositivo_id)
            continue
        if isinstance(lecturas, list):
            lecturas_por_dispositivo.append([x for x in lecturas if isinstance(x, dict)])

    serie = _agregar_serie_planta(lecturas_por_dispositivo)
    p_kw = [b["p_kw"] for b in serie if b["p_kw"] is not None]
    q_kvar = [b["q_kvar"] for b in serie if b["q_kvar"] is not None]
    fps = [b["fp"] for b in serie if b["fp"] is not None]

    return {
        "planta_id": planta_id,
        "horas": horas,
        "metodo": "suma por bucket de 5 min de los dispositivos de la planta",
        "dispositivos_consultados": len(ids),
        "dispositivos_con_error": con_error,
        "puntos_medicion_count": len(serie),
        "potencia_activa_promedio_kw": round(_promedio(p_kw), 2) if p_kw else None,
        "potencia_activa_max_kw": round(max(p_kw), 2) if p_kw else None,
        "potencia_reactiva_promedio_kvar": round(_promedio(q_kvar), 2) if q_kvar else None,
        "potencia_reactiva_max_kvar": round(max(q_kvar), 2) if q_kvar else None,
        "factor_potencia_promedio": round(_promedio(fps), 3) if fps else None,
    }


def main() -> None:
    """Punto de entrada principal para ejecutar el servidor MCP en modo stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
