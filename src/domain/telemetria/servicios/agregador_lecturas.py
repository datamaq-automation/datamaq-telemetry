"""src/domain/telemetria/servicios/agregador_lecturas.py — Servicio para remuestreo y agregación temporal de lecturas instantáneas."""

from dataclasses import replace
from datetime import datetime, timezone

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.calculos_potencia import CalculadoraPotenciaService
from src.domain.telemetria.servicios.promedio_subbloques import promedio_por_subbloques
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


def _con_potencias_por_subbloques(
    agregada: LecturaInstantanea,
    items: list[LecturaInstantanea],
    intervalo_segundos: int,
) -> LecturaInstantanea:
    """P y Q del bloque como media de sus sub-bloques de 5 min (decisión 2026-10-11).

    S y FP del bloque siguen con el promedio de muestras de `_agregar_grupo_lecturas`.
    """

    def _epoch(it: LecturaInstantanea) -> float:
        reg = it.registrado_en if it.registrado_en.tzinfo is not None else it.registrado_en.replace(tzinfo=timezone.utc)
        return reg.timestamp()

    p = promedio_por_subbloques(
        [(_epoch(it), it.potencia_activa_total.vatios) for it in items if it.potencia_activa_total is not None],
        intervalo_segundos,
    )
    q = promedio_por_subbloques(
        [(_epoch(it), it.potencia_reactiva_total.var) for it in items if it.potencia_reactiva_total is not None],
        intervalo_segundos,
    )
    return replace(
        agregada,
        potencia_activa_total=PotenciaActiva(vatios=p) if p is not None else agregada.potencia_activa_total,
        potencia_reactiva_total=PotenciaReactiva(var=q) if q is not None else agregada.potencia_reactiva_total,
    )


class AgregadorLecturasService:
    """Agrupa y remuestrea lecturas instantáneas en buckets de tiempo fijos."""

    @staticmethod
    def _promedio_valores(vals: list[float | None]) -> float | None:
        non_none = [v for v in vals if v is not None]
        if not non_none:
            return None
        return round(sum(non_none) / len(non_none), 2)

    @classmethod
    def _calcular_fase_agregada(cls, fases: list[MedicionFase]) -> MedicionFase:
        v = cls._promedio_valores([f.tension.voltios for f in fases if f.tension])
        i = cls._promedio_valores([f.corriente.amperios for f in fases if f.corriente])
        p = cls._promedio_valores([f.potencia_activa.vatios for f in fases if f.potencia_activa])
        q = cls._promedio_valores([f.potencia_reactiva.var for f in fases if f.potencia_reactiva])
        s = CalculadoraPotenciaService.calcular_potencia_aparente(v, i)
        if s is None:
            s = cls._promedio_valores([f.potencia_aparente.va for f in fases if f.potencia_aparente])
        fp = CalculadoraPotenciaService.calcular_factor_potencia(p, s)
        if fp is None:
            fp = cls._promedio_valores([f.factor_potencia.valor for f in fases if f.factor_potencia])
        thd_v = cls._promedio_valores([f.thd_v_porcentaje for f in fases if f.thd_v_porcentaje is not None])
        thd_i = cls._promedio_valores([f.thd_i_porcentaje for f in fases if f.thd_i_porcentaje is not None])
        return MedicionFase(
            tension=Tension(voltios=v) if v is not None else None,
            corriente=Corriente(amperios=i) if i is not None else None,
            potencia_activa=PotenciaActiva(vatios=p) if p is not None else None,
            potencia_reactiva=PotenciaReactiva(var=q) if q is not None else None,
            potencia_aparente=PotenciaAparente(va=s) if s is not None else None,
            factor_potencia=FactorPotencia(valor=fp) if fp is not None else None,
            thd_v_porcentaje=thd_v,
            thd_i_porcentaje=thd_i,
        )

    @classmethod
    def _calcular_totales_potencia(
        cls,
        items: list[LecturaInstantanea],
        fase_r: MedicionFase,
        fase_s: MedicionFase,
        fase_t: MedicionFase,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        p_tot = cls._promedio_valores([it.potencia_activa_total.vatios for it in items if it.potencia_activa_total])
        if p_tot is None:
            p_sub = [f.potencia_activa.vatios for f in (fase_r, fase_s, fase_t) if f.potencia_activa]
            if p_sub:
                p_tot = round(sum(p_sub), 2)

        q_tot = cls._promedio_valores([it.potencia_reactiva_total.var for it in items if it.potencia_reactiva_total])
        if q_tot is None:
            q_sub = [f.potencia_reactiva.var for f in (fase_r, fase_s, fase_t) if f.potencia_reactiva]
            if q_sub:
                q_tot = round(sum(q_sub), 2)

        s_tot = CalculadoraPotenciaService.calcular_potencia_aparente_total(
            *(f.potencia_aparente.va if f.potencia_aparente else None for f in (fase_r, fase_s, fase_t))
        )
        if s_tot is None:
            s_tot = cls._promedio_valores([it.potencia_aparente_total.va for it in items if it.potencia_aparente_total])

        fp_tot = CalculadoraPotenciaService.calcular_factor_potencia(p_tot, s_tot)
        if fp_tot is None:
            fp_tot = cls._promedio_valores([it.factor_potencia_total.valor for it in items if it.factor_potencia_total])

        return p_tot, q_tot, s_tot, fp_tot

    @classmethod
    def _calcular_red_electrica(
        cls,
        fase_r: MedicionFase,
        fase_s: MedicionFase,
        fase_t: MedicionFase,
        es_monofasico: bool,
    ) -> tuple[float | None, float | None, Corriente | None, float | None]:
        if es_monofasico:
            return None, None, None, None

        from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
            AnalizadorMetrologicoService,
        )

        vr = fase_r.tension.voltios if fase_r.tension else None
        vs = fase_s.tension.voltios if fase_s.tension else None
        vt = fase_t.tension.voltios if fase_t.tension else None
        desbalance_v = AnalizadorMetrologicoService.calcular_desbalance_tension(vr, vs, vt)

        tensiones_fase = [v for v in (vr, vs, vt) if v is not None]
        voltage_linea_V = None
        if tensiones_fase:
            promedio_fase = sum(tensiones_fase) / len(tensiones_fase)
            voltage_linea_V = round(promedio_fase * 1.7320508075688772, 2)

        ir_val = fase_r.corriente.amperios if fase_r.corriente else None
        is_val = fase_s.corriente.amperios if fase_s.corriente else None
        it_val = fase_t.corriente.amperios if fase_t.corriente else None
        pr_val = fase_r.potencia_activa.vatios if fase_r.potencia_activa else None
        ps_val = fase_s.potencia_activa.vatios if fase_s.potencia_activa else None
        pt_val = fase_t.potencia_activa.vatios if fase_t.potencia_activa else None
        qr_val = fase_r.potencia_reactiva.var if fase_r.potencia_reactiva else None
        qs_val = fase_s.potencia_reactiva.var if fase_s.potencia_reactiva else None
        qt_val = fase_t.potencia_reactiva.var if fase_t.potencia_reactiva else None

        i_neutro = AnalizadorMetrologicoService.calcular_corriente_neutro(
            ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
        )
        v_neutro = AnalizadorMetrologicoService.calcular_tension_neutro(
            vr, vs, vt, ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
        )
        return desbalance_v, voltage_linea_V, i_neutro, v_neutro

    @classmethod
    def _calcular_thd_agregado(
        cls,
        items: list[LecturaInstantanea],
        fase_r: MedicionFase,
        fase_s: MedicionFase,
        fase_t: MedicionFase,
    ) -> tuple[float | None, float | None]:
        thd_v_prom = cls._promedio_valores(
            [it.thd_v_promedio_porcentaje for it in items if it.thd_v_promedio_porcentaje is not None]
        )
        if thd_v_prom is None:
            thd_v_vals = [
                (f.thd_v_porcentaje if f.thd_v_porcentaje is not None else f.thd_v_pct)
                for f in (fase_r, fase_s, fase_t)
                if (f.thd_v_porcentaje is not None or f.thd_v_pct is not None)
            ]
            if thd_v_vals:
                thd_v_prom = cls._promedio_valores(thd_v_vals)

        thd_i_tot = cls._promedio_valores(
            [it.thd_i_total_porcentaje for it in items if it.thd_i_total_porcentaje is not None]
        )
        if thd_i_tot is None:
            thd_i_vals = [
                (f.thd_i_porcentaje if f.thd_i_porcentaje is not None else f.thd_i_pct)
                for f in (fase_r, fase_s, fase_t)
                if (f.thd_i_porcentaje is not None or f.thd_i_pct is not None)
            ]
            if thd_i_vals:
                thd_i_tot = cls._promedio_valores(thd_i_vals)

        return thd_v_prom, thd_i_tot

    @staticmethod
    def _pico_potencia_activa(items: list[LecturaInstantanea]) -> float | None:
        """Máximo de la potencia activa total de las muestras del bloque (W)."""
        valores = [it.potencia_activa_total.vatios for it in items if it.potencia_activa_total is not None]
        valores = [v for v in valores if v is not None]
        return max(valores) if valores else None

    @classmethod
    def _agregar_grupo_lecturas(
        cls,
        items: list[LecturaInstantanea],
        bucket_dt: datetime,
        es_monofasico: bool = False,
    ) -> LecturaInstantanea:
        dispositivo_id = items[0].dispositivo_id

        fase_r = cls._calcular_fase_agregada([it.fase_r for it in items])
        fase_s = cls._calcular_fase_agregada([it.fase_s for it in items])
        fase_t = cls._calcular_fase_agregada([it.fase_t for it in items])

        p_tot, q_tot, s_tot, fp_tot = cls._calcular_totales_potencia(items, fase_r, fase_s, fase_t)
        desbalance_v, voltage_linea_V, i_neutro, v_neutro = cls._calcular_red_electrica(
            fase_r, fase_s, fase_t, es_monofasico
        )
        thd_v_prom, thd_i_tot = cls._calcular_thd_agregado(items, fase_r, fase_s, fase_t)

        return LecturaInstantanea(
            id=None,
            dispositivo_id=dispositivo_id,
            registrado_en=bucket_dt,
            fase_r=fase_r,
            fase_s=fase_s,
            fase_t=fase_t,
            potencia_activa_total=PotenciaActiva(vatios=p_tot) if p_tot is not None else None,
            potencia_reactiva_total=PotenciaReactiva(var=q_tot) if q_tot is not None else None,
            potencia_aparente_total=PotenciaAparente(va=s_tot) if s_tot is not None else None,
            factor_potencia_total=FactorPotencia(valor=fp_tot) if fp_tot is not None else None,
            desbalance_tension_porcentaje=desbalance_v,
            corriente_neutro_estimada=i_neutro,
            voltage_linea_V=voltage_linea_V,
            tension_neutro_estimada=v_neutro,
            thd_v_promedio_porcentaje=thd_v_prom,
            thd_i_total_porcentaje=thd_i_tot,
            demanda_max_w=cls._pico_potencia_activa(items),
        )

    @classmethod
    def agregar_lecturas_en_intervalo(
        cls,
        lecturas: list[LecturaInstantanea],
        intervalo_segundos: int,
        es_monofasico: bool = False,
    ) -> list[LecturaInstantanea]:
        """Agrupa y remuestrea una lista de LecturaInstantanea en buckets de tiempo fijos."""
        if intervalo_segundos <= 0 or not lecturas:
            return lecturas

        buckets: dict[int, list[LecturaInstantanea]] = {}
        for item in lecturas:
            reg = item.registrado_en
            if reg.tzinfo is None:
                reg = reg.replace(tzinfo=timezone.utc)
            ts = reg.timestamp()
            bucket_ts = int(ts // intervalo_segundos) * intervalo_segundos
            if bucket_ts not in buckets:
                buckets[bucket_ts] = []
            buckets[bucket_ts].append(item)

        resultado = []
        for bucket_ts in sorted(buckets.keys(), reverse=True):
            bucket_items = buckets[bucket_ts]
            bucket_dt = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
            agregada = cls._agregar_grupo_lecturas(bucket_items, bucket_dt, es_monofasico=es_monofasico)
            resultado.append(_con_potencias_por_subbloques(agregada, bucket_items, intervalo_segundos))

        return resultado

    @staticmethod
    def _obtener_x_y(item: LecturaInstantanea) -> tuple[float, float]:
        reg = item.registrado_en
        if reg.tzinfo is None:
            reg = reg.replace(tzinfo=timezone.utc)
        x = reg.timestamp()
        y = (
            item.potencia_activa_total.vatios
            if item.potencia_activa_total and item.potencia_activa_total.vatios is not None
            else 0.0
        )
        return x, y

    @classmethod
    def _calcular_centroide_bucket(
        cls,
        next_bucket: list[LecturaInstantanea],
        ultimo_dato: LecturaInstantanea,
    ) -> tuple[float, float]:
        if next_bucket:
            next_x_sum = sum(cls._obtener_x_y(it)[0] for it in next_bucket)
            next_y_sum = sum(cls._obtener_x_y(it)[1] for it in next_bucket)
            return next_x_sum / len(next_bucket), next_y_sum / len(next_bucket)
        return cls._obtener_x_y(ultimo_dato)

    @classmethod
    def downsample_lttb(
        cls,
        lecturas: list[LecturaInstantanea],
        target_points: int,
    ) -> list[LecturaInstantanea]:
        """Reduce la serie temporal a target_points usando Largest-Triangle-Three-Buckets (LTTB)."""
        if not lecturas or target_points <= 0 or len(lecturas) <= target_points:
            return lecturas

        if target_points == 1:
            return [lecturas[0]]
        if target_points == 2:
            return [lecturas[0], lecturas[-1]]

        es_descendente = lecturas[0].registrado_en > lecturas[-1].registrado_en
        datos = list(reversed(lecturas)) if es_descendente else list(lecturas)

        n = len(datos)
        bucket_size = (n - 2) / (target_points - 2)
        resultado = [datos[0]]
        a_idx = 0

        for i in range(target_points - 2):
            next_start = int((i + 1) * bucket_size) + 1
            next_end = min(int((i + 2) * bucket_size) + 1, n)
            c_x, c_y = cls._calcular_centroide_bucket(datos[next_start:next_end], datos[-1])

            curr_start = int(i * bucket_size) + 1
            curr_end = min(int((i + 1) * bucket_size) + 1, n)
            curr_bucket = datos[curr_start:curr_end]

            a_x, a_y = cls._obtener_x_y(datos[a_idx])
            max_area, max_idx = -1.0, curr_start

            for j, candidate in enumerate(curr_bucket):
                idx = curr_start + j
                b_x, b_y = cls._obtener_x_y(candidate)
                area = abs((a_x - c_x) * (b_y - a_y) - (a_x - b_x) * (c_y - a_y)) * 0.5
                if area > max_area:
                    max_area, max_idx = area, idx

            resultado.append(datos[max_idx])
            a_idx = max_idx

        resultado.append(datos[-1])
        if es_descendente:
            resultado.reverse()
        return resultado
