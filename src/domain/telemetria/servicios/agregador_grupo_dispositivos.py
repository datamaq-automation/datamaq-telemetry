"""src/domain/telemetria/servicios/agregador_grupo_dispositivos.py."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.domain.telemetria.entities import EnergiaAgregada, LecturaInstantanea


@dataclass(frozen=True)
class PotenciaSumadaGrupo:
    """Suma de la última lectura conocida de cada dispositivo miembro de un grupo.

    ``dispositivos_sin_dato`` lista los device_id sin ninguna lectura instantánea
    todavía, para que la UI pueda avisar que el total es parcial.
    """

    potencia_activa_total_w: float | None
    dispositivos_sin_dato: list[str]


@dataclass(frozen=True)
class PuntoPotenciaGrupo:
    """Un punto de la serie de tiempo de potencia sumada de un grupo (un bucket)."""

    momento: datetime
    potencia_activa_total_w: float | None
    dispositivos_sin_dato: list[str]


class AgregadorGrupoDispositivosService:
    """Suma lecturas de varios dispositivos ya resueltas por dispositivo, sin acceso a I/O.

    Tolera desalineamiento temporal entre dispositivos a propósito (confirmado con el
    negocio): suma la última lectura conocida de cada uno, no exige timestamps iguales.
    """

    @staticmethod
    def sumar_ultimas_lecturas(
        lecturas_por_dispositivo: dict[str, LecturaInstantanea | None],
    ) -> PotenciaSumadaGrupo:
        total = 0.0
        hubo_dato = False
        sin_dato: list[str] = []
        for dispositivo_id, lectura in lecturas_por_dispositivo.items():
            if lectura is None or lectura.potencia_activa_total is None:
                sin_dato.append(dispositivo_id)
                continue
            total += lectura.potencia_activa_total.vatios
            hubo_dato = True
        return PotenciaSumadaGrupo(
            potencia_activa_total_w=round(total, 2) if hubo_dato else None,
            dispositivos_sin_dato=sin_dato,
        )

    @staticmethod
    def sumar_energia_agregada(
        agregados_por_dispositivo: dict[str, list[EnergiaAgregada]],
    ) -> list[EnergiaAgregada]:
        totales_por_periodo: dict[date, float] = {}
        hubo_dato_por_periodo: dict[date, bool] = {}
        for agregados in agregados_por_dispositivo.values():
            for item in agregados:
                if item.energia_activa_neta_kwh is None:
                    totales_por_periodo.setdefault(item.periodo, 0.0)
                    hubo_dato_por_periodo.setdefault(item.periodo, False)
                    continue
                totales_por_periodo[item.periodo] = (
                    totales_por_periodo.get(item.periodo, 0.0) + item.energia_activa_neta_kwh
                )
                hubo_dato_por_periodo[item.periodo] = True

        return [
            EnergiaAgregada(
                periodo=periodo,
                energia_activa_neta_kwh=round(totales_por_periodo[periodo], 4)
                if hubo_dato_por_periodo.get(periodo)
                else None,
            )
            for periodo in sorted(totales_por_periodo)
        ]

    @staticmethod
    def sumar_potencia_en_el_tiempo(
        lecturas_por_dispositivo: dict[str, list[tuple[datetime, float | None]]],
        intervalo_segundos: int,
    ) -> list[PuntoPotenciaGrupo]:
        """Bucketiza por tiempo (mismo cálculo de piso que AgregadorLecturasService) y suma
        entre dispositivos. Tolera que cada dispositivo tenga sus propios timestamps: lo que
        importa es a qué bucket cae cada lectura, no que coincidan exactamente entre sí.
        """
        totales_por_bucket: dict[int, float] = {}
        hubo_dato_por_bucket: dict[int, bool] = {}
        dispositivos_con_dato_por_bucket: dict[int, set[str]] = {}
        todos_los_buckets: set[int] = set()

        for dispositivo_id, lecturas in lecturas_por_dispositivo.items():
            for momento, potencia_w in lecturas:
                m = momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)
                bucket_ts = int(m.timestamp() // intervalo_segundos) * intervalo_segundos
                todos_los_buckets.add(bucket_ts)
                if potencia_w is None:
                    hubo_dato_por_bucket.setdefault(bucket_ts, False)
                    continue
                totales_por_bucket[bucket_ts] = totales_por_bucket.get(bucket_ts, 0.0) + potencia_w
                hubo_dato_por_bucket[bucket_ts] = True
                dispositivos_con_dato_por_bucket.setdefault(bucket_ts, set()).add(dispositivo_id)

        todos_los_dispositivos = set(lecturas_por_dispositivo.keys())
        resultado = []
        for bucket_ts in sorted(todos_los_buckets):
            con_dato = dispositivos_con_dato_por_bucket.get(bucket_ts, set())
            resultado.append(
                PuntoPotenciaGrupo(
                    momento=datetime.fromtimestamp(bucket_ts, tz=timezone.utc),
                    potencia_activa_total_w=round(totales_por_bucket[bucket_ts], 2)
                    if hubo_dato_por_bucket.get(bucket_ts)
                    else None,
                    dispositivos_sin_dato=sorted(todos_los_dispositivos - con_dato),
                )
            )
        return resultado
