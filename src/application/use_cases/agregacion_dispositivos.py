"""src/application/use_cases/agregacion_dispositivos.py.

Lógica de I/O compartida para agregar telemetría de una lista de device ids —
usada tanto por grupos de dispositivos como por nodos del unifilar. La única
diferencia entre ambos consumidores es de dónde sacan esa lista de ids
(``grupo.dispositivos_ids`` vs. ``ArbolUnifilarService.medidores_frontera``);
el cálculo de suma en sí vive en ``AgregadorDispositivosService``.
"""

import math
import time
from datetime import datetime, timedelta, timezone

import structlog

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import EnergiaAgregada
from src.domain.telemetria.ports import RepositorioTelemetriaPort
from src.domain.telemetria.servicios.agregador_dispositivos import (
    AgregadorDispositivosService,
    PotenciaSumada,
    PuntoPotencia,
)
from src.domain.telemetria.servicios.potencia_referencia import (
    GRANULARIDAD_REFERENCIA,
    VENTANA_REFERENCIA_HORAS,
    potencia_referencia,
)

_log = structlog.get_logger(__name__)


def calcular_resumen(
    dispositivos_ids: list[str],
    repo_telemetria: RepositorioTelemetriaPort,
    consultar_telemetria: ConsultarTelemetriaUseCase,
    granularidad: str,
    zona: str,
    dias: int | None,
    relacion_transformacion: float = 1.0,
) -> tuple[PotenciaSumada, list[EnergiaAgregada]]:
    """``relacion_transformacion`` lo decide ``derivar_relacion_transformacion``
    a partir del nodo y su frontera; acá ya llega resuelto como escalar."""
    _log.debug(
        "agregador_resumen_inicio",
        dispositivos_count=len(dispositivos_ids),
        dispositivos_ids=dispositivos_ids,
        relacion_transformacion=relacion_transformacion,
    )

    lecturas_por_dispositivo = {
        dispositivo_id: repo_telemetria.obtener_ultima_instantanea(dispositivo_id)
        for dispositivo_id in dispositivos_ids
    }
    potencia_sumada = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas_por_dispositivo)
    agregado_por_fase = AgregadorDispositivosService.sumar_fases(lecturas_por_dispositivo, relacion_transformacion)
    potencia_sumada = PotenciaSumada(
        potencia_activa_total_w=potencia_sumada.potencia_activa_total_w,
        dispositivos_sin_dato=potencia_sumada.dispositivos_sin_dato,
        potencia_reactiva_total_var=potencia_sumada.potencia_reactiva_total_var,
        potencia_aparente_total_va=potencia_sumada.potencia_aparente_total_va,
        factor_desplazamiento_total=potencia_sumada.factor_desplazamiento_total,
        registrado_en=potencia_sumada.registrado_en,
        agregado_por_fase=agregado_por_fase,
    )

    agregados_por_dispositivo: dict[str, list[EnergiaAgregada]] = {}
    for dispositivo_id in dispositivos_ids:
        agregados_dto = consultar_telemetria.listar_energia_agregada(dispositivo_id, granularidad, zona, dias)
        agregados_por_dispositivo[dispositivo_id] = [
            EnergiaAgregada(periodo=a.periodo, energia_activa_neta_kwh=a.energia_activa_neta_kwh) for a in agregados_dto
        ]
    energia_sumada = AgregadorDispositivosService.sumar_energia_agregada(agregados_por_dispositivo)
    return potencia_sumada, energia_sumada


def calcular_datos_desde(
    dispositivos_ids: list[str],
    consultar_telemetria: ConsultarTelemetriaUseCase,
) -> datetime | None:
    """Corte de retención más reciente entre los dispositivos: desde ahí están todos, así la suma
    nunca queda incompleta sin aviso (D3). ``None`` si no hay dispositivos."""
    cortes = [consultar_telemetria.datos_desde(dispositivo_id) for dispositivo_id in dispositivos_ids]
    return max(cortes) if cortes else None


def calcular_historico(
    dispositivos_ids: list[str],
    consultar_telemetria: ConsultarTelemetriaUseCase,
    granularidad: str,
    horas: int,
    hasta: datetime | None = None,
) -> list[PuntoPotencia]:
    _log.debug(
        "agregador_historico_inicio",
        dispositivos_count=len(dispositivos_ids),
        dispositivos_ids=dispositivos_ids,
        granularidad=granularidad,
        horas=horas,
        hasta=hasta.isoformat() if hasta else None,
    )

    intervalo_segundos = ConsultarTelemetriaUseCase._resolver_intervalo_segundos(granularidad, horas)
    if intervalo_segundos <= 0:
        intervalo_segundos = 300

    # Un intervalo por bucket de la ventana (+1 por el bucket parcial del borde): con un tope fijo
    # de 2000, una semana a 5 min (2016 buckets) perdía sus ~80 min más antiguos.
    limite = max(2000, math.ceil(horas * 3600 / intervalo_segundos) + 1)
    desde = (hasta or datetime.now(timezone.utc)) - timedelta(hours=horas)

    lecturas_por_dispositivo: dict[str, list[tuple]] = {}
    for dispositivo_id in dispositivos_ids:
        lecturas_dto = consultar_telemetria.listar_instantaneas(
            dispositivo_id, limite=limite, desde=desde, granularidad=granularidad, horas=horas, hasta=hasta
        )
        lecturas_por_dispositivo[dispositivo_id] = [
            (lectura.registrado_en, lectura.potencia_activa_total_W, lectura.potencia_reactiva_total_VAR)
            for lectura in lecturas_dto
        ]

    return AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas_por_dispositivo, intervalo_segundos)


def calcular_potencia_referencia(
    dispositivos_ids: list[str],
    consultar_telemetria: ConsultarTelemetriaUseCase,
) -> float | None:
    """P99 de la potencia activa de la serie **sumada** de los dispositivos en los últimos 30 días,
    acotada por el corte de retención (D1, D2). No se suman P99 individuales: los picos de cada
    medidor no son simultáneos y esa suma sobreestima. Con un solo id es el P99 del medidor.
    ``None`` si no hay datos suficientes (``MINIMO_HORAS_CON_DATOS``)."""
    if not dispositivos_ids:
        return None
    inicio = time.perf_counter()
    datos_desde = calcular_datos_desde(dispositivos_ids, consultar_telemetria)
    puntos = calcular_historico(
        dispositivos_ids, consultar_telemetria, GRANULARIDAD_REFERENCIA, VENTANA_REFERENCIA_HORAS
    )
    muestras = [
        (p.momento, p.potencia_activa_total_w)
        for p in puntos
        if p.potencia_activa_total_w is not None and (datos_desde is None or p.momento >= datos_desde)
    ]
    referencia = potencia_referencia(muestras)
    # Solo corre al vencer la caché (15 min): mide el costo real del cálculo en producción.
    _log.info(
        "potencia_referencia_calculada",
        dispositivos_count=len(dispositivos_ids),
        muestras=len(muestras),
        referencia_w=referencia,
        duracion_ms=round((time.perf_counter() - inicio) * 1000),
    )
    return referencia
