"""src/domain/telemetria/servicios/agregador_dispositivos.py."""

import bisect
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from src.domain.telemetria.entities import EnergiaAgregada, LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.tensiones_de_linea import tensiones_de_linea


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
    agregado_por_fase: "AgregadoPorFase | None" = None


@dataclass(frozen=True)
class FaseAgregada:
    """Magnitudes eléctricas agregadas para una única fase (R, S o T).

    - ``voltage_V``: promedio de tensiones (V no se suman — representan el estado de la red).
    - ``current_A``: suma de corrientes (Kirchhoff).
    - ``net_active_power_W`` / ``net_reactive_power_VAR``: suma directa.
    - ``net_apparent_power_VA`` / ``power_factor``: recompuestos desde P y Q agregados.
    - ``desbalance_tension_pct``: calculado sobre las tensiones promedio de las 3 fases.
    """

    voltage_V: float | None
    current_A: float | None
    net_active_power_W: float | None
    net_reactive_power_VAR: float | None
    net_apparent_power_VA: float | None
    power_factor: float | None
    desbalance_tension_pct: float | None


@dataclass(frozen=True)
class AgregadoPorFase:
    """Contenedor de las tres fases agregadas de un nodo.

    Las tensiones compuestas van acá y no dentro de ``FaseAgregada`` porque una
    tensión de línea pertenece a un *par* de fases, no a una fase: no existe "la
    compuesta de R". Se derivan de las fase-neutro ya escaladas a la escala del
    nodo, así que quedan en esa misma escala.
    """

    fase_r: FaseAgregada
    fase_s: FaseAgregada
    fase_t: FaseAgregada
    tension_linea_rs_V: float | None = None
    tension_linea_st_V: float | None = None
    tension_linea_tr_V: float | None = None


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
    dispositivos_interpolados: list[str] = field(default_factory=list)
    """Medidores cuyo dato de este bucket es una interpolación lineal entre lecturas vecinas (#94).

    Aditivo: ``dispositivos_sin_dato`` sigue listando a todos los medidores sin lectura en el bucket.
    """


# Un medidor sin lectura en un bucket se interpola solo si la lectura anterior y la posterior
# están a no más de este tiempo del bucket. Más lejos, el hueco queda como suma parcial (#94).
MAX_DISTANCIA_INTERPOLACION_S = 900


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
        # Si un medidor absorbe un hueco en un periodo, la suma de ese periodo también lo absorbe.
        sin_datos_por_periodo: dict[date, int] = {}
        for agregados in agregados_por_dispositivo.values():
            for item in agregados:
                sin_datos_por_periodo[item.periodo] = max(
                    sin_datos_por_periodo.get(item.periodo, 0), item.periodos_sin_datos_previos
                )
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
                periodos_sin_datos_previos=sin_datos_por_periodo.get(periodo, 0),
            )
            for periodo in sorted(totales_por_periodo)
        ]

    @staticmethod
    def sumar_potencia_en_el_tiempo(
        lecturas_por_dispositivo: dict[str, list[tuple]],
        intervalo_segundos: int,
    ) -> list[PuntoPotencia]:
        """Bucketiza por tiempo (mismo cálculo de piso que AgregadorLecturasService), promedia las
        lecturas de cada dispositivo dentro del bucket y suma esos promedios entre dispositivos. Tolera que cada dispositivo tenga sus propios timestamps: lo que
        importa es a qué bucket cae cada lectura, no que coincidan exactamente entre sí.

        Cada lectura es ``(momento, potencia_activa_w)`` o ``(momento, potencia_activa_w,
        potencia_reactiva_var)``.
        """
        # Muestras por (bucket, dispositivo): varias lecturas de un mismo medidor en un bucket
        # (p. ej. las crudas del buffer en vivo antepuestas al histórico ya agregado) son muestras
        # de UNA potencia media. Se promedian por medidor y recién después se suma entre medidores.
        muestras_p: dict[tuple[int, str], list[float]] = {}
        muestras_q: dict[tuple[int, str], list[float]] = {}
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
                muestras_p.setdefault((bucket_ts, dispositivo_id), []).append(potencia_w)
                hubo_dato_por_bucket[bucket_ts] = True
                dispositivos_con_dato_por_bucket.setdefault(bucket_ts, set()).add(dispositivo_id)
                if reactiva_var is None:
                    q_completa_por_bucket[bucket_ts] = False
                else:
                    q_completa_por_bucket.setdefault(bucket_ts, True)
                    muestras_q.setdefault((bucket_ts, dispositivo_id), []).append(reactiva_var)

        # Interpolación de huecos (#94). Un medidor sin lectura en un bucket, con lectura anterior y
        # posterior a no más de 15 min del bucket, aporta su P (y Q) interpolada linealmente. Se usan
        # solo lecturas reales como vecinas, sin encadenar buckets interpolados.
        promedio_p = {clave: sum(v) / len(v) for clave, v in muestras_p.items()}
        promedio_q = {clave: sum(v) / len(v) for clave, v in muestras_q.items()}
        interpolados_por_bucket: dict[int, list[str]] = {}
        for dispositivo_id in sorted(lecturas_por_dispositivo):
            serie = sorted(b for (b, d) in muestras_p if d == dispositivo_id)
            if len(serie) < 2:
                continue
            for bucket_ts in sorted(todos_los_buckets):
                if (bucket_ts, dispositivo_id) in muestras_p:
                    continue
                i = bisect.bisect_left(serie, bucket_ts)
                if i == 0 or i == len(serie):
                    continue  # borde de la ventana: no hay vecino a un lado
                b_ant, b_sig = serie[i - 1], serie[i]
                if (
                    bucket_ts - b_ant > MAX_DISTANCIA_INTERPOLACION_S
                    or b_sig - bucket_ts > MAX_DISTANCIA_INTERPOLACION_S
                ):
                    continue
                peso = (bucket_ts - b_ant) / (b_sig - b_ant)
                p_ant = promedio_p[(b_ant, dispositivo_id)]
                p_sig = promedio_p[(b_sig, dispositivo_id)]
                promedio_p[(bucket_ts, dispositivo_id)] = p_ant + peso * (p_sig - p_ant)
                if (b_ant, dispositivo_id) in promedio_q and (b_sig, dispositivo_id) in promedio_q:
                    q_ant = promedio_q[(b_ant, dispositivo_id)]
                    q_sig = promedio_q[(b_sig, dispositivo_id)]
                    promedio_q[(bucket_ts, dispositivo_id)] = q_ant + peso * (q_sig - q_ant)
                else:
                    q_completa_por_bucket[bucket_ts] = False
                interpolados_por_bucket.setdefault(bucket_ts, []).append(dispositivo_id)

        totales_p_por_bucket = _sumar_promedios_por_bucket({c: [v] for c, v in promedio_p.items()})
        totales_q_por_bucket = _sumar_promedios_por_bucket({c: [v] for c, v in promedio_q.items()})

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
                    dispositivos_interpolados=sorted(interpolados_por_bucket.get(bucket_ts, [])),
                )
            )
        return resultado

    @staticmethod
    def sumar_fases(
        lecturas_por_dispositivo: dict[str, "LecturaInstantanea | None"],
        relacion_transformacion: float = 1.0,
    ) -> "AgregadoPorFase | None":
        """Agrega magnitudes eléctricas por fase (R, S, T) de múltiples dispositivos.

        Para nodos BT usar ``relacion_transformacion=1.0`` (default).
        Para nodos MT pasar ``a = V_primario_kV / V_secundario_kV`` obtenido de
        ``MetadatosPlaca.relacion_tension_kv`` (ej: "15/0.4" → 37.5).

        Bajo la hipótesis de transformador ideal:
        - V_fase_MT = V_fase_BT x a
        - I_fase_MT = I_fase_BT / a
        - P, Q, S, FP: invariantes (conservación de energía).
        """
        sum_v, cnt_v, sum_i, sum_p, sum_q, q_completa, hubo_dato = _acumular_lecturas_fase(lecturas_por_dispositivo)
        if not hubo_dato:
            return None

        v_prom = {
            k: round((sum_v[k] / cnt_v[k]) * relacion_transformacion, 1) if cnt_v[k] > 0 else None
            for k in ("r", "s", "t")
        }
        i_sum = {k: round(sum_i[k] / relacion_transformacion, 2) if sum_i[k] > 0 else None for k in ("r", "s", "t")}
        desbalance = _calcular_desbalance_tension(v_prom)

        def _fase(k: str) -> FaseAgregada:
            p = round(sum_p[k], 2) if sum_p[k] != 0.0 else None
            q_val = sum_q[k]
            q = round(q_val, 2) if q_completa[k] and q_val is not None else None
            s, fp = _recomponer_s_y_cos_fi(p, q)
            return FaseAgregada(
                voltage_V=v_prom[k],
                current_A=i_sum[k],
                net_active_power_W=p,
                net_reactive_power_VAR=q,
                net_apparent_power_VA=s,
                power_factor=fp,
                desbalance_tension_pct=desbalance,
            )

        v_rs, v_st, v_tr = tensiones_de_linea(v_prom["r"], v_prom["s"], v_prom["t"])
        return AgregadoPorFase(
            fase_r=_fase("r"),
            fase_s=_fase("s"),
            fase_t=_fase("t"),
            tension_linea_rs_V=v_rs,
            tension_linea_st_V=v_st,
            tension_linea_tr_V=v_tr,
        )


def _sumar_promedios_por_bucket(muestras: dict[tuple[int, str], list[float]]) -> dict[int, float]:
    """Promedia las muestras de cada (bucket, dispositivo) y suma esos promedios por bucket."""
    totales: dict[int, float] = {}
    for (bucket_ts, _), valores in muestras.items():
        totales[bucket_ts] = totales.get(bucket_ts, 0.0) + sum(valores) / len(valores)
    return totales


def _calcular_desbalance_tension(v_prom: dict[str, float | None]) -> float | None:
    tensiones_disponibles = [v for v in v_prom.values() if v is not None]
    if len(tensiones_disponibles) == 3:
        v_max = max(tensiones_disponibles)
        v_min = min(tensiones_disponibles)
        v_media = sum(tensiones_disponibles) / 3
        return round((v_max - v_min) / v_media * 100, 2) if v_media > 0 else None
    return None


def _acumular_medicion_fase(
    fase: "MedicionFase",
    clave: str,
    sum_v: dict[str, float],
    cnt_v: dict[str, int],
    sum_i: dict[str, float],
    sum_p: dict[str, float],
    sum_q: dict[str, float | None],
    q_completa: dict[str, bool],
) -> None:
    if fase.tension is not None:
        sum_v[clave] += fase.tension.voltios
        cnt_v[clave] += 1
    if fase.corriente is not None:
        sum_i[clave] += fase.corriente.amperios
    if fase.potencia_activa is not None:
        sum_p[clave] += fase.potencia_activa.vatios
    if fase.potencia_reactiva is not None and q_completa[clave]:
        sum_q[clave] = (sum_q[clave] or 0.0) + fase.potencia_reactiva.var
    elif fase.potencia_activa is not None and fase.potencia_reactiva is None:
        q_completa[clave] = False


def _acumular_lecturas_fase(
    lecturas_por_dispositivo: dict[str, "LecturaInstantanea | None"],
) -> tuple[
    dict[str, float], dict[str, int], dict[str, float], dict[str, float], dict[str, float | None], dict[str, bool], bool
]:
    sum_v: dict[str, float] = {"r": 0.0, "s": 0.0, "t": 0.0}
    cnt_v: dict[str, int] = {"r": 0, "s": 0, "t": 0}
    sum_i: dict[str, float] = {"r": 0.0, "s": 0.0, "t": 0.0}
    sum_p: dict[str, float] = {"r": 0.0, "s": 0.0, "t": 0.0}
    sum_q: dict[str, float | None] = {"r": 0.0, "s": 0.0, "t": 0.0}
    q_completa: dict[str, bool] = {"r": True, "s": True, "t": True}
    hubo_dato = False

    fase_map = [
        ("r", lambda lect: lect.fase_r),
        ("s", lambda lect: lect.fase_s),
        ("t", lambda lect: lect.fase_t),
    ]

    for lectura in lecturas_por_dispositivo.values():
        if lectura is None or lectura.potencia_activa_total is None:
            continue
        hubo_dato = True
        for clave, getter in fase_map:
            _acumular_medicion_fase(getter(lectura), clave, sum_v, cnt_v, sum_i, sum_p, sum_q, q_completa)

    return sum_v, cnt_v, sum_i, sum_p, sum_q, q_completa, hubo_dato
