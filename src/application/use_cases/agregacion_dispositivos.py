"""src/application/use_cases/agregacion_dispositivos.py.

Lógica de I/O compartida para agregar telemetría de una lista de device ids —
usada tanto por grupos de dispositivos como por nodos del unifilar. La única
diferencia entre ambos consumidores es de dónde sacan esa lista de ids
(``grupo.dispositivos_ids`` vs. ``ArbolUnifilarService.medidores_frontera``);
el cálculo de suma en sí vive en ``AgregadorDispositivosService``.
"""

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.entities import EnergiaAgregada
from src.domain.telemetria.ports import RepositorioTelemetriaPort
from src.domain.telemetria.servicios.agregador_dispositivos import (
    AgregadorDispositivosService,
    PotenciaSumada,
    PuntoPotencia,
)


def _parsear_relacion_transformacion(relacion_tension_kv: str | None) -> float:
    """Parsea "15/0.4" → 37.5. Retorna 1.0 si no se puede parsear (nodo BT)."""
    if not relacion_tension_kv:
        return 1.0
    try:
        partes = relacion_tension_kv.split("/")
        if len(partes) != 2:
            return 1.0
        primario, secundario = float(partes[0]), float(partes[1])
        return primario / secundario if secundario > 0 else 1.0
    except ValueError:
        return 1.0


def calcular_resumen(
    dispositivos_ids: list[str],
    repo_telemetria: RepositorioTelemetriaPort,
    consultar_telemetria: ConsultarTelemetriaUseCase,
    granularidad: str,
    zona: str,
    dias: int | None,
    relacion_tension_kv: str | None = None,
) -> tuple[PotenciaSumada, list[EnergiaAgregada]]:
    lecturas_por_dispositivo = {
        dispositivo_id: repo_telemetria.obtener_ultima_instantanea(dispositivo_id)
        for dispositivo_id in dispositivos_ids
    }
    relacion = _parsear_relacion_transformacion(relacion_tension_kv)
    potencia_sumada = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas_por_dispositivo)
    agregado_por_fase = AgregadorDispositivosService.sumar_fases(lecturas_por_dispositivo, relacion)
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


def calcular_historico(
    dispositivos_ids: list[str],
    consultar_telemetria: ConsultarTelemetriaUseCase,
    granularidad: str,
    horas: int,
) -> list[PuntoPotencia]:
    intervalo_segundos = ConsultarTelemetriaUseCase._resolver_intervalo_segundos(granularidad, horas)
    if intervalo_segundos <= 0:
        intervalo_segundos = 300

    lecturas_por_dispositivo: dict[str, list[tuple]] = {}
    for dispositivo_id in dispositivos_ids:
        lecturas_dto = consultar_telemetria.listar_instantaneas(
            dispositivo_id, limite=2000, granularidad=granularidad, horas=horas
        )
        lecturas_por_dispositivo[dispositivo_id] = [
            (lectura.registrado_en, lectura.potencia_activa_total_W, lectura.potencia_reactiva_total_VAR)
            for lectura in lecturas_dto
        ]

    return AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas_por_dispositivo, intervalo_segundos)
