"""tools/mcp/server.py — Servidor MCP (Model Context Protocol) para DataMaq.

Expone herramientas de diagnóstico y analítica energética para Claude Desktop y Claude Code
utilizando FastMCP sobre transporte stdio y cliente HTTP httpx.
"""

import math
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
    """Retorna las plantas industriales a las que el usuario autenticado tiene acceso en DataMaq.

    Las plantas agrupan uno o más medidores de energía eléctrica (tableros generales,
    trafos o celdas de media tensión). Toda la analítica y diagnósticos posteriores se
    agregan a nivel planta sumando vectorialmente las mediciones de sus dispositivos.
    """
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
    """Lista las alertas eléctricas y operativas aisladas para la planta especificada.

    Aisla y enriquece las alertas correspondientes a los medidores de la planta con
    `planta_id` y `dispositivo_tag`. Discrimina alertas por bajo factor de potencia según
    los criterios normativos:
    - Umbral tarifario clásico de distribuidoras (FP < 0.85): penalizaciones severas y recargos.
    - Umbral normativo regulatorio vigente ENRE 85/2024 (FP < 0.95): requerimiento federal
      de eficiencia y base de dimensionamiento de bancos de capacitores.

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

    Calcula la potencia reactiva necesaria para alcanzar el factor de potencia objetivo normativo
    ENRE 85/2024 (FP >= 0.95, típicamente objetivo 0.96) a partir de la integración vectorial
    de potencia activa (kW) y reactiva (kVAr) de todos los medidores de la planta en la ventana.
    Distingue la compensación regulatoria (meta 0.95) del límite de recargos tarifarios (0.85).

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

    Evalúa los intervalos donde el factor de potencia global de la planta desciende por debajo
    del umbral tarifario contractual (0.85), a partir de mediciones reales agregadas a nivel planta.
    Permite parametrizar la ventana de análisis (`periodo_dias`, 1 a 30 días, por defecto 7).
    Distingue el umbral tarifario de penalización (0.85) del estándar normativo ENRE 85/2024 (0.95).

    Args:
        planta_id: Identificador único de la planta industrial.
        periodo_dias: Ventana de análisis en días (por defecto 7, de 1 a 30 días).
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


def _promedios_por_bucket(lecturas: list[dict[str, Any]]) -> dict[int, tuple[float | None, float | None]]:
    """P y Q promedio de UN dispositivo por bucket de 5 min."""
    acumulado: dict[int, tuple[list[float], list[float]]] = {}
    for lectura in lecturas:
        marca = lectura.get("registrado_en")
        if not isinstance(marca, str):
            continue
        instante = datetime.fromisoformat(marca.replace("Z", "+00:00"))
        ps, qs = acumulado.setdefault(int(instante.timestamp()) // _BUCKET_SEGUNDOS, ([], []))
        p_w = lectura.get("potencia_activa_total_W")
        q_var = lectura.get("potencia_reactiva_total_VAR")
        if p_w is not None:
            ps.append(float(p_w))
        if q_var is not None:
            qs.append(float(q_var))
    return {
        clave: (sum(ps) / len(ps) if ps else None, sum(qs) / len(qs) if qs else None)
        for clave, (ps, qs) in acumulado.items()
    }


def _agregar_serie_planta(lecturas_por_dispositivo: list[list[dict[str, Any]]]) -> list[dict[str, float | None]]:
    """Promedia P y Q de cada dispositivo por bucket de 5 min, los suma entre dispositivos y calcula FP vectorial.

    El promedio por dispositivo es necesario: /instantaneous antepone las lecturas crudas del buffer en vivo (una cada
    pocos segundos en modo tiempo real), que caen todas en el último bucket. Sumarlas tal cual multiplicaba la potencia
    por la cantidad de lecturas: el "pico" de 22 811 kW de Durax eran ~40 lecturas de ~570 kW (#18). Es el mismo
    criterio que AgregadorDispositivosService en el backend (40d9dda).
    """
    buckets: dict[int, dict[str, Any]] = {}
    for lecturas in lecturas_por_dispositivo:
        for clave, (p_w, q_var) in _promedios_por_bucket(lecturas).items():
            bucket = buckets.setdefault(clave, {"p_w": None, "q_var": None})
            if p_w is not None:
                bucket["p_w"] = (bucket["p_w"] or 0.0) + p_w
            if q_var is not None:
                bucket["q_var"] = (bucket["q_var"] or 0.0) + q_var

    resultado = []
    for _, b in sorted(buckets.items()):
        p_w = b["p_w"]
        q_var = b["q_var"]
        p_kw = p_w / 1000.0 if p_w is not None else None
        q_kvar = q_var / 1000.0 if q_var is not None else None

        fp_bucket = None
        if p_w is not None or q_var is not None:
            p_val = p_w or 0.0
            q_val = q_var or 0.0
            s_val = math.sqrt(p_val**2 + q_val**2)
            if s_val > 0:
                fp_bucket = abs(p_val) / s_val

        resultado.append(
            {
                "p_kw": p_kw,
                "q_kvar": q_kvar,
                "fp": fp_bucket,
            }
        )
    return resultado


def _promedio(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


# Compuerta de calidad de datos (#31). Los umbrales siguen a los del backend para que el MCP no contradiga las alertas.
_UMBRAL_P_NEGATIVA_W = -100.0  # evaluador_potencia_negativa.py:22
_FRACCION_BUCKETS_NEGATIVOS = 0.5  # sostenida: la mitad o más de los buckets con dato
_COBERTURA_MEDIDOR_MINIMA_PCT = 80.0  # mismo criterio que la advertencia de planta (abajo, en potencia_reciente)
_FASES_TRIFASICAS = ("R", "S", "T")
_CATEGORIAS_POLARIDAD = frozenset({"POLARIDAD_TI", "TI_INVERTIDO"})
_CODIGOS_BLOQUEANTES = frozenset({"S1", "S2"})


def _fases_desde_config(fases_con_ti: str | None) -> tuple[list[str], list[str]]:
    """Fases medidas y faltantes a partir de `fases_con_ti` ('R,S', 'R,S,T'...). Sin dato, se asume trifásico."""
    if not fases_con_ti:
        return list(_FASES_TRIFASICAS), []
    medidas = [f.strip().upper() for f in fases_con_ti.split(",") if f.strip().upper() in _FASES_TRIFASICAS]
    faltantes = [f for f in _FASES_TRIFASICAS if f not in medidas]
    return medidas, faltantes


def _evaluar_medidor(
    dispositivo: dict[str, Any],
    lecturas: list[dict[str, Any]],
    alertas_abiertas: list[dict[str, Any]],
    puntos_esperados: int,
) -> dict[str, Any]:
    """Evalúa un medidor con los códigos de sospecha S1 a S4 (ver spec-issue-31.md, sección 2)."""
    dispositivo_id = dispositivo.get("id")
    tipo = (dispositivo.get("tipo_instalacion") or "CONSUMO").upper()
    medidas, faltantes = _fases_desde_config(dispositivo.get("fases_con_ti"))
    codigos: list[str] = []

    polaridad_abierta = any(
        a.get("dispositivo_id") == dispositivo_id
        and (a.get("tipo_alerta") in _CATEGORIAS_POLARIDAD or a.get("categoria") in _CATEGORIAS_POLARIDAD)
        for a in alertas_abiertas
    )
    if polaridad_abierta:
        codigos.append("S1")

    # Se mira el signo de P antes de cualquier abs(): con `abs`, una P invertida daría un FP plausible.
    p_por_bucket = [p for p, _ in _promedios_por_bucket(lecturas).values() if p is not None]
    if tipo == "CONSUMO" and p_por_bucket:
        negativos = sum(1 for p in p_por_bucket if p < _UMBRAL_P_NEGATIVA_W)
        if negativos / len(p_por_bucket) >= _FRACCION_BUCKETS_NEGATIVOS:
            codigos.append("S2")

    cobertura_pct = round(len(p_por_bucket) / puntos_esperados * 100, 1) if puntos_esperados > 0 else 0.0
    if cobertura_pct < _COBERTURA_MEDIDOR_MINIMA_PCT:
        codigos.append("S3")
    if faltantes:
        codigos.append("S4")

    return {
        "dispositivo_id": dispositivo_id,
        "ubicacion_tag": dispositivo.get("ubicacion_tag") or dispositivo_id,
        "tipo_instalacion": tipo,
        "fases_medidas": medidas,
        "fases_faltantes": faltantes,
        "cobertura_puntos_pct": cobertura_pct,
        "codigos": codigos,
    }


def _resumen_calidad(evaluaciones: list[dict[str, Any]]) -> dict[str, Any]:
    """Medidores sospechosos y cobertura trifásica de la planta. Una fase faltante nunca cuenta como cero."""
    sospechosos = [e for e in evaluaciones if e["codigos"]]
    no_trifasicos = [e for e in evaluaciones if e["fases_faltantes"]]
    return {
        "medidores_sospechosos": sospechosos,
        "total_trifasico_completo": not no_trifasicos,
        "dispositivos_no_trifasicos": [
            {"dispositivo_id": e["dispositivo_id"], "fases_faltantes": e["fases_faltantes"]} for e in no_trifasicos
        ],
    }


def _bloquea_calculo(evaluaciones: list[dict[str, Any]]) -> bool:
    """S1 o S2 en algún medidor: el signo de P no es confiable y el cálculo de kVAr o importes no se entrega."""
    return any(_CODIGOS_BLOQUEANTES & set(e["codigos"]) for e in evaluaciones)


@mcp.tool()
async def datamaq_consultar_potencia_reciente(
    planta_id: str,
    horas: int = 24,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Consulta el resumen de demanda activa (kW) y reactiva (kVAr) de una planta en una ventana reciente.

    Recorre los medidores de la planta agregando vectorialmente las potencias activa (P) y
    reactiva (Q) por bucket de 5 min (S = sqrt(P^2 + Q^2), FP = |P| / S). El factor de potencia
    promedio del período se calcula sobre las sumas acumuladas vectoriales conforme a la regulación
    ENRE/CAMMESA, evitando distorsiones aritméticas en plantas multi-medidor.
    Incluye porcentaje de cobertura de mediciones y advertencia si es menor al 80%.
    Permite evaluar el desempeño frente al umbral tarifario (0.85) y normativo ENRE 85/2024 (0.95).

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

    p_acum = sum(p_kw) if p_kw else 0.0
    q_acum = sum(q_kvar) if q_kvar else 0.0
    denominador = math.sqrt(p_acum**2 + q_acum**2)
    fp_global = (abs(p_acum) / denominador) if denominador > 0 else None

    puntos_esperados = (horas * 3600) // 300
    puntos_count = len(serie)
    cobertura_puntos_pct = round((puntos_count / puntos_esperados) * 100, 1) if puntos_esperados > 0 else 0.0

    respuesta: dict[str, Any] = {
        "planta_id": planta_id,
        "horas": horas,
        "metodo": "promedio por dispositivo y suma entre dispositivos, por bucket de 5 min",
        "dispositivos_consultados": len(ids),
        "dispositivos_con_error": con_error,
        "puntos_medicion_count": puntos_count,
        "cobertura_puntos_pct": cobertura_puntos_pct,
        "potencia_activa_promedio_kw": round(_promedio(p_kw), 2) if p_kw else None,
        "potencia_activa_max_kw": round(max(p_kw), 2) if p_kw else None,
        "potencia_reactiva_promedio_kvar": round(_promedio(q_kvar), 2) if q_kvar else None,
        "potencia_reactiva_max_kvar": round(max(q_kvar), 2) if q_kvar else None,
        "factor_potencia_promedio": round(fp_global, 3) if fp_global is not None else None,
    }
    if cobertura_puntos_pct < 80.0:
        respuesta["advertencia_datos"] = "Datos incompletos (<80% de cobertura)"

    return respuesta


def main() -> None:
    """Punto de entrada principal para ejecutar el servidor MCP en modo stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
