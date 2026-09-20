"""src/domain/telemetria/servicios/agregador_dispositivos.py."""

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.domain.telemetria.entities import EnergiaAgregada, LecturaInstantanea


@dataclass(frozen=True)
class PotenciaSumada:
    """Suma de la última lectura conocida de cada dispositivo miembro de un grupo.

    ``dispositivos_sin_dato`` lista los device_id sin ninguna lectura instantánea
    todavía, para que la UI pueda avisar que el total es parcial.

    ``factor_desplazamiento_total`` es cos φ (P/S recompuesto solo de la componente
    fundamental de P y Q), NO el factor de potencia real que mide cada dispositivo
    (``LecturaInstantanea.factor_potencia_total``), que incluye el efecto de la
    distorsión armónica (THD). Con cargas no lineales (variadores de frecuencia,
    rectificadores) ambos valores difieren; el que penaliza la tarifa es el real medido
    por equipo, no este agregado. Agregar el FP real de varios dispositivos con THD
    distinto no es una simple suma de P/Q — requeriría datos de distorsión por
    dispositivo, que este servicio no usa.
    """

    potencia_activa_total_w: float | None
    dispositivos_sin_dato: list[str]
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None
    registrado_en: datetime | None = None


@dataclass(frozen=True)
class PuntoPotencia:
    """Un punto de la serie de tiempo de potencia sumada de un grupo (un bucket).

    Ver ``PotenciaSumada`` para la salvedad de ``factor_desplazamiento_total``
    (cos φ, no el FP real con armónicos).
    """

    momento: datetime
    potencia_activa_total_w: float | None
    dispositivos_sin_dato: list[str]
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None


def _recomponer_s_y_cos_fi(p_w: float | None, q_var: float | None) -> tuple[float | None, float | None]:
    """Recompone S y cos φ (factor de desplazamiento) del P y Q ya sumados.

    S y FP no son aditivas entre dispositivos: hay que sumar P y Q por separado y
    recién ahí recomponer. Da cos φ, no el FP real con distorsión armónica.
    """
    if p_w is None or q_var is None:
        return None, None
    s_va = math.hypot(p_w, q_var)
    if s_va == 0.0:
        return 0.0, None
    return round(s_va, 2), round(p_w / s_va, 4)


class AgregadorDispositivosService:
    """Suma lecturas de varios dispositivos ya resueltas por dispositivo, sin acceso a I/O.

    Tolera desalineamiento temporal entre dispositivos a propósito (confirmado con el
    negocio): suma la última lectura conocida de cada uno, no exige timestamps iguales.

    Q se suma con signo (inductiva +, capacitiva -). Si algún dispositivo con P no
    reporta Q, el total de Q (y por ende S y FP) queda en None en vez de recomponerse
    con datos parciales.
    """

    @staticmethod
    def sumar_ultimas_lecturas(
        lecturas_por_dispositivo: dict[str, LecturaInstantanea | None],
    ) -> PotenciaSumada:
        total_p = 0.0
        total_q = 0.0
        hubo_dato = False
        q_completa = True
        sin_dato: list[str] = []
        timestamps: list[datetime] = []
        for dispositivo_id, lectura in lecturas_por_dispositivo.items():
            if lectura is None or lectura.potencia_activa_total is None:
                sin_dato.append(dispositivo_id)
                continue
            total_p += lectura.potencia_activa_total.vatios
            hubo_dato = True
            timestamps.append(lectura.registrado_en)
            if lectura.potencia_reactiva_total is None:
                q_completa = False
            else:
                total_q += lectura.potencia_reactiva_total.var

        p = round(total_p, 2) if hubo_dato else None
        q = round(total_q, 2) if hubo_dato and q_completa else None
        s, fp = _recomponer_s_y_cos_fi(p, q)
        return PotenciaSumada(
            potencia_activa_total_w=p,
            dispositivos_sin_dato=sin_dato,
            potencia_reactiva_total_var=q,
            potencia_aparente_total_va=s,
            factor_desplazamiento_total=fp,
            registrado_en=max(timestamps) if timestamps else None,
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
        lecturas_por_dispositivo: dict[str, list[tuple]],
        intervalo_segundos: int,
    ) -> list[PuntoPotencia]:
        """Bucketiza por tiempo (mismo cálculo de piso que AgregadorLecturasService) y suma
        entre dispositivos. Tolera que cada dispositivo tenga sus propios timestamps: lo que
        importa es a qué bucket cae cada lectura, no que coincidan exactamente entre sí.

        Cada lectura es ``(momento, potencia_activa_w)`` o ``(momento, potencia_activa_w,
        potencia_reactiva_var)``.
        """
        totales_p_por_bucket: dict[int, float] = {}
        totales_q_por_bucket: dict[int, float] = {}
        hubo_dato_por_bucket: dict[int, bool] = {}
        q_completa_por_bucket: dict[int, bool] = {}
        dispositivos_con_dato_por_bucket: dict[int, set[str]] = {}
        todos_los_buckets: set[int] = set()

        for dispositivo_id, lecturas in lecturas_por_dispositivo.items():
            for lectura in lecturas:
                momento, potencia_w = lectura[0], lectura[1]
                reactiva_var = lectura[2] if len(lectura) > 2 else None
                m = momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)
                bucket_ts = int(m.timestamp() // intervalo_segundos) * intervalo_segundos
                todos_los_buckets.add(bucket_ts)
                if potencia_w is None:
                    hubo_dato_por_bucket.setdefault(bucket_ts, False)
                    continue
                totales_p_por_bucket[bucket_ts] = totales_p_por_bucket.get(bucket_ts, 0.0) + potencia_w
                hubo_dato_por_bucket[bucket_ts] = True
                dispositivos_con_dato_por_bucket.setdefault(bucket_ts, set()).add(dispositivo_id)
                if reactiva_var is None:
                    q_completa_por_bucket[bucket_ts] = False
                else:
                    q_completa_por_bucket.setdefault(bucket_ts, True)
                    totales_q_por_bucket[bucket_ts] = totales_q_por_bucket.get(bucket_ts, 0.0) + reactiva_var

        todos_los_dispositivos = set(lecturas_por_dispositivo.keys())
        resultado = []
        for bucket_ts in sorted(todos_los_buckets):
            con_dato = dispositivos_con_dato_por_bucket.get(bucket_ts, set())
            hubo_dato = hubo_dato_por_bucket.get(bucket_ts, False)
            p = round(totales_p_por_bucket[bucket_ts], 2) if hubo_dato else None
            q = (
                round(totales_q_por_bucket[bucket_ts], 2)
                if hubo_dato and q_completa_por_bucket.get(bucket_ts)
                else None
            )
            s, fp = _recomponer_s_y_cos_fi(p, q)
            resultado.append(
                PuntoPotencia(
                    momento=datetime.fromtimestamp(bucket_ts, tz=timezone.utc),
                    potencia_activa_total_w=p,
                    dispositivos_sin_dato=sorted(todos_los_dispositivos - con_dato),
                    potencia_reactiva_total_var=q,
                    potencia_aparente_total_va=s,
                    factor_desplazamiento_total=fp,
                )
            )
        return resultado
