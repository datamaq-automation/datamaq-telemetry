"""tools/mcp/server.py — Servidor MCP (Model Context Protocol) para DataMaq.

Expone herramientas de diagnóstico y analítica energética para Claude Desktop y Claude Code
utilizando FastMCP sobre transporte stdio y cliente HTTP httpx.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    parametros: dict[str, Any] = {
        "planta_id": planta_id,
        "solo_abiertas": solo_abiertas,
    }
    resultado = await _ejecutar_peticion("GET", "/api/v1/alertas", token=token, params=parametros)
    if isinstance(resultado, list):
        return resultado
    return [resultado]


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


@mcp.tool()
async def datamaq_consultar_potencia_reciente(
    planta_id: str,
    horas: int = 24,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Consulta el resumen de demanda activa (kW) y reactiva (kVAr) de una planta en una ventana de horas reciente.

    Args:
        planta_id: Identificador único de la planta industrial.
        horas: Cantidad de horas recientes a consultar (por defecto 24).
        ctx: Contexto de ejecución FastMCP inyectado automáticamente.
    """
    token = _resolver_token(ctx)
    parametros: dict[str, Any] = {
        "planta_id": planta_id,
        "horas": horas,
    }
    resultado = await _ejecutar_peticion("GET", "/api/v1/telemetria/rango", token=token, params=parametros)

    if isinstance(resultado, dict):
        return resultado

    if isinstance(resultado, list) and resultado:
        p_activa = [
            float(p["potencia_activa_total_kw"])
            if "potencia_activa_total_kw" in p and p["potencia_activa_total_kw"] is not None
            else (float(p.get("potencia_activa_total_w", 0.0)) / 1000.0)
            for p in resultado
            if isinstance(p, dict)
        ]
        q_reactiva = [
            float(p["potencia_reactiva_total_kvar"])
            if "potencia_reactiva_total_kvar" in p and p["potencia_reactiva_total_kvar"] is not None
            else (float(p.get("potencia_reactiva_total_var", 0.0)) / 1000.0)
            for p in resultado
            if isinstance(p, dict)
        ]
        fps = [
            float(p["factor_potencia_total"])
            for p in resultado
            if isinstance(p, dict) and p.get("factor_potencia_total") is not None
        ]

        return {
            "planta_id": planta_id,
            "horas": horas,
            "puntos_medicion_count": len(resultado),
            "potencia_activa_promedio_kw": round(sum(p_activa) / len(p_activa), 2) if p_activa else None,
            "potencia_activa_max_kw": round(max(p_activa), 2) if p_activa else None,
            "potencia_reactiva_promedio_kvar": round(sum(q_reactiva) / len(q_reactiva), 2) if q_reactiva else None,
            "potencia_reactiva_max_kvar": round(max(q_reactiva), 2) if q_reactiva else None,
            "factor_potencia_promedio": round(sum(fps) / len(fps), 3) if fps else None,
        }

    return {
        "planta_id": planta_id,
        "horas": horas,
        "puntos_medicion_count": 0,
        "mensaje": "Sin registros de telemetría disponibles para el período seleccionado",
    }


def main() -> None:
    """Punto de entrada principal para ejecutar el servidor MCP en modo stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
