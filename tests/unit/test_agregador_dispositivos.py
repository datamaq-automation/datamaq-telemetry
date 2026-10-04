"""tests/unit/test_agregador_dispositivos.py — suma vectorial de lecturas de varios medidores (nodos virtuales del unifilar)."""

from datetime import date, datetime, timezone

from src.domain.telemetria.entities import EnergiaAgregada, LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.agregador_dispositivos import AgregadorDispositivosService
from src.domain.telemetria.value_objects import PotenciaActiva, PotenciaReactiva


def _lectura(dispositivo_id: str, vatios: float, var: float | None = None) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=datetime(2026, 9, 1, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios),
        potencia_reactiva_total=PotenciaReactiva(var) if var is not None else None,
    )


class TestAgregadorDispositivosService:
    def test_suma_potencia_de_dispositivos_con_dato(self):
        lecturas = {"trafo-01": _lectura("trafo-01", 1000.0), "trafo-02": _lectura("trafo-02", 1500.0)}
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 2500.0
        assert resultado.dispositivos_sin_dato == []

    def test_suma_p_y_q_por_separado_y_recompone_s_y_fp(self):
        # P = 3000+1000 = 4000 W; Q = 4000 + (-1000) = 3000 var (capacitiva resta) → S = 5000 VA, FP = 0.8
        lecturas = {
            "trafo-01": _lectura("trafo-01", 3000.0, var=4000.0),
            "trafo-02": _lectura("trafo-02", 1000.0, var=-1000.0),
        }
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 4000.0
        assert resultado.potencia_reactiva_total_var == 3000.0
        assert resultado.potencia_aparente_total_va == 5000.0
        assert resultado.factor_desplazamiento_total == 0.8

    def test_s_no_es_suma_de_las_s_individuales(self):
        # S1 = 5000 (3000+4000j), S2 = 5000 (3000-4000j); suma vectorial: P=6000, Q=0 → S=6000, no 10000
        lecturas = {
            "trafo-01": _lectura("trafo-01", 3000.0, var=4000.0),
            "trafo-02": _lectura("trafo-02", 3000.0, var=-4000.0),
        }
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_aparente_total_va == 6000.0
        assert resultado.factor_desplazamiento_total == 1.0

    def test_q_parcial_deja_q_s_y_fp_en_none(self):
        lecturas = {
            "trafo-01": _lectura("trafo-01", 3000.0, var=4000.0),
            "trafo-02": _lectura("trafo-02", 1000.0),
        }
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 4000.0
        assert resultado.potencia_reactiva_total_var is None
        assert resultado.potencia_aparente_total_va is None
        assert resultado.factor_desplazamiento_total is None

    def test_sumar_potencia_en_el_tiempo_recompone_s_y_fp_por_bucket(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 3000.0, 4000.0), (base.replace(minute=5), 1000.0, None)],
            "trafo-02": [(base, 1000.0, -1000.0), (base.replace(minute=5), 1000.0, 500.0)],
        }
        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)
        assert resultado[0].potencia_activa_total_w == 4000.0
        assert resultado[0].potencia_reactiva_total_var == 3000.0
        assert resultado[0].potencia_aparente_total_va == 5000.0
        assert resultado[0].factor_desplazamiento_total == 0.8
        # Segundo bucket: trafo-01 sin Q → no se recompone
        assert resultado[1].potencia_activa_total_w == 2000.0
        assert resultado[1].potencia_reactiva_total_var is None
        assert resultado[1].factor_desplazamiento_total is None

    def test_suma_tolera_desalineamiento_y_avisa_dispositivo_sin_dato(self):
        lecturas = {"trafo-01": _lectura("trafo-01", 1000.0), "trafo-02": None}
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 1000.0
        assert resultado.dispositivos_sin_dato == ["trafo-02"]

    def test_suma_sin_ningun_dato_devuelve_none(self):
        lecturas = {"trafo-01": None, "trafo-02": None}
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w is None
        assert resultado.dispositivos_sin_dato == ["trafo-01", "trafo-02"]

    def test_suma_energia_agregada_por_periodo_entre_dispositivos(self):

        agregados = {
            "trafo-01": [
                EnergiaAgregada(periodo=date(2026, 9, 1), energia_activa_neta_kwh=None),
                EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=10.0),
            ],
            "trafo-02": [
                EnergiaAgregada(periodo=date(2026, 9, 1), energia_activa_neta_kwh=None),
                EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=5.0),
            ],
        }
        resultado = AgregadorDispositivosService.sumar_energia_agregada(agregados)
        por_periodo = {r.periodo: r.energia_activa_neta_kwh for r in resultado}
        assert por_periodo[date(2026, 9, 1)] is None
        assert por_periodo[date(2026, 9, 2)] == 15.0

    def test_suma_energia_con_un_dispositivo_sin_dato_en_el_periodo(self):

        agregados = {
            "trafo-01": [EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=10.0)],
            "trafo-02": [EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=None)],
        }
        resultado = AgregadorDispositivosService.sumar_energia_agregada(agregados)
        assert resultado[0].energia_activa_neta_kwh == 10.0

    def test_sumar_potencia_en_el_tiempo_alinea_por_bucket_pese_a_desalineamiento(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0), (base.replace(minute=5), 1100.0)],
            # Mismo bucket de 5 minutos que el primero, pero con timestamp corrido 40s.
            "trafo-02": [(base.replace(second=40), 500.0), (base.replace(minute=5, second=10), 600.0)],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 2
        assert resultado[0].potencia_activa_total_w == 1500.0
        assert resultado[0].dispositivos_sin_dato == []
        assert resultado[1].potencia_activa_total_w == 1700.0

    def test_sumar_potencia_en_el_tiempo_marca_dispositivo_sin_dato_en_un_bucket(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0)],
            "trafo-02": [],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w == 1000.0
        assert resultado[0].dispositivos_sin_dato == ["trafo-02"]

    def test_sumar_potencia_en_el_tiempo_sin_ningun_dato_en_bucket_es_none(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, None)],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w is None

    def test_sumar_potencia_nodo_virtual_media_tension_agregacion_correcta(self):
        """Verifica que la agregación del nodo virtual de Media Tensión suma exactamente las potencias
        en Vatios (W = P_trafo1 + P_trafo2) sin aplicar doble factor de transformación ni errores de magnitud.
        """

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        # Trafo 1: 450,000 W (450 kW), Trafo 2: 350,000 W (350 kW)
        p_trafo1_w = 450000.0
        p_trafo2_w = 350000.0
        q_trafo1_var = 150000.0
        q_trafo2_var = 100000.0

        lecturas = {
            "dev-trafo-1": [(base, p_trafo1_w, q_trafo1_var)],
            "dev-trafo-2": [(base, p_trafo2_w, q_trafo2_var)],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        punto = resultado[0]

        # P_total = P_trafo1 + P_trafo2 = 800,000 W (800 kW <= 2000 kVA capacidad nominal)
        assert punto.potencia_activa_total_w == 800000.0
        assert punto.potencia_reactiva_total_var == 250000.0
        assert punto.dispositivos_sin_dato == []
        # Potencia aparente S = sqrt(800000^2 + 250000^2) ≈ 838152.73 VA
        assert punto.potencia_aparente_total_va == 838152.73

    def test_sumar_potencia_en_el_tiempo_promedia_lecturas_del_mismo_dispositivo_en_un_bucket(self):
        """Varias lecturas de un mismo medidor en un bucket (p. ej. las crudas del buffer en vivo que
        ``listar_instantaneas`` antepone al histórico agregado) son muestras de UNA potencia media, no
        maquinas distintas: sumarlas multiplicaba el último bucket del nodo MT (pico de 72 a 92 MW)."""

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [
                (base, 1000.0, 100.0),
                (base.replace(second=10), 2000.0, 200.0),
                (base.replace(second=20), 3000.0, 300.0),
            ],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w == 2000.0
        assert resultado[0].potencia_reactiva_total_var == 200.0

    def test_sumar_potencia_en_el_tiempo_suma_promedios_entre_dispositivos(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0, 100.0), (base.replace(second=30), 3000.0, 300.0)],
            "trafo-02": [(base.replace(second=40), 500.0, 50.0)],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w == 2500.0
        assert resultado[0].potencia_reactiva_total_var == 250.0
        assert resultado[0].dispositivos_sin_dato == []

    def test_sumar_potencia_en_el_tiempo_ignora_lecturas_none_al_promediar(self):

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0), (base.replace(second=10), None), (base.replace(second=20), 3000.0)],
        }

        resultado = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert resultado[0].potencia_activa_total_w == 2000.0

    def test_registrado_en_es_el_timestamp_mas_reciente_entre_dispositivos_con_dato(self):
        ts_antiguo = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts_reciente = datetime(2026, 9, 1, 10, 5, 0, tzinfo=timezone.utc)
        lecturas: dict[str, LecturaInstantanea | None] = {
            "dev-01": LecturaInstantanea(
                id=None,
                dispositivo_id="dev-01",
                registrado_en=ts_antiguo,
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(1000.0),
                potencia_reactiva_total=None,
            ),
            "dev-02": LecturaInstantanea(
                id=None,
                dispositivo_id="dev-02",
                registrado_en=ts_reciente,
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(500.0),
                potencia_reactiva_total=None,
            ),
        }
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)

        assert resultado.registrado_en == ts_reciente

    def test_registrado_en_es_none_cuando_todos_los_dispositivos_sin_dato(self):
        lecturas: dict[str, LecturaInstantanea | None] = {
            "dev-01": None,
            "dev-02": None,
        }
        resultado = AgregadorDispositivosService.sumar_ultimas_lecturas(lecturas)

        assert resultado.registrado_en is None
        assert resultado.potencia_activa_total_w is None

    # ------------------------------------------------------------------
    # sumar_fases
    # ------------------------------------------------------------------

    def _lectura_completa(
        self,
        dispositivo_id: str,
        v_r: float,
        v_s: float,
        v_t: float,
        i_r: float,
        i_s: float,
        i_t: float,
        p_r: float,
        p_s: float,
        p_t: float,
    ) -> LecturaInstantanea:
        from src.domain.telemetria.value_objects import Corriente, Tension

        return LecturaInstantanea(
            id=None,
            dispositivo_id=dispositivo_id,
            registrado_en=datetime(2026, 9, 1, tzinfo=timezone.utc),
            fase_r=MedicionFase(tension=Tension(v_r), corriente=Corriente(i_r), potencia_activa=PotenciaActiva(p_r)),
            fase_s=MedicionFase(tension=Tension(v_s), corriente=Corriente(i_s), potencia_activa=PotenciaActiva(p_s)),
            fase_t=MedicionFase(tension=Tension(v_t), corriente=Corriente(i_t), potencia_activa=PotenciaActiva(p_t)),
            potencia_activa_total=PotenciaActiva(p_r + p_s + p_t),
            potencia_reactiva_total=None,
        )

    def test_sumar_fases_suma_potencias_promedia_tension_y_suma_corriente(self):
        lect1 = self._lectura_completa("d1", 230.0, 231.0, 229.0, 10.0, 10.0, 10.0, 2300.0, 2310.0, 2290.0)
        lect2 = self._lectura_completa("d2", 232.0, 233.0, 231.0, 12.0, 12.0, 12.0, 2784.0, 2796.0, 2772.0)
        resultado = AgregadorDispositivosService.sumar_fases({"d1": lect1, "d2": lect2})

        assert resultado is not None
        # Tensión: promedio de los 2 dispositivos
        assert resultado.fase_r.voltage_V == round((230.0 + 232.0) / 2, 1)  # 231.0
        assert resultado.fase_s.voltage_V == round((231.0 + 233.0) / 2, 1)  # 232.0
        assert resultado.fase_t.voltage_V == round((229.0 + 231.0) / 2, 1)  # 230.0
        # Corriente: suma
        assert resultado.fase_r.current_A == round(10.0 + 12.0, 2)  # 22.0
        # Potencia activa: suma
        assert resultado.fase_r.net_active_power_W == round(2300.0 + 2784.0, 2)  # 5084.0
        # Desbalance de tensión: (232.0 - 230.0) / 231.0 * 100 ≈ 0.87%
        assert resultado.fase_r.desbalance_tension_pct is not None

    def test_sumar_fases_excluye_fase_null_de_dispositivo_monofasico(self):
        """Un dispositivo monofásico reporta solo fase_r; sus fase_s y fase_t están en None."""
        from src.domain.telemetria.value_objects import Corriente, Tension

        trifasico = self._lectura_completa("tri", 230.0, 231.0, 229.0, 10.0, 10.0, 10.0, 2300.0, 2310.0, 2290.0)
        monofasico = LecturaInstantanea(
            id=None,
            dispositivo_id="mono",
            registrado_en=datetime(2026, 9, 1, tzinfo=timezone.utc),
            fase_r=MedicionFase(
                tension=Tension(228.0), corriente=Corriente(8.0), potencia_activa=PotenciaActiva(1824.0)
            ),
            fase_s=MedicionFase(),  # null — monofásico no reporta S
            fase_t=MedicionFase(),  # null — monofásico no reporta T
            potencia_activa_total=PotenciaActiva(1824.0),
            potencia_reactiva_total=None,
        )
        resultado = AgregadorDispositivosService.sumar_fases({"tri": trifasico, "mono": monofasico})

        assert resultado is not None
        # fase_r: promedio de 2 dispositivos (230 + 228) / 2
        assert resultado.fase_r.voltage_V == round((230.0 + 228.0) / 2, 1)
        # fase_s: solo el trifásico (monofásico tenía None)
        assert resultado.fase_s.voltage_V == 231.0
        assert resultado.fase_t.voltage_V == 229.0

    def test_sumar_fases_devuelve_none_si_todos_sin_dato(self):
        resultado = AgregadorDispositivosService.sumar_fases({"d1": None, "d2": None})
        assert resultado is None

    def test_sumar_fases_aplica_relacion_transformacion_mt(self):
        """Con relacion de transformacion 15/0.4 = 37.5: V x 37.5, I/37.5, P invariante."""
        lect = self._lectura_completa("d1", 230.0, 231.0, 229.0, 34.8, 34.8, 34.8, 5000.0, 5000.0, 5000.0)
        resultado = AgregadorDispositivosService.sumar_fases({"d1": lect}, relacion_transformacion=37.5)

        assert resultado is not None
        # Tension MT: 230.0 x 37.5 = 8625.0 V
        assert resultado.fase_r.voltage_V == round(230.0 * 37.5, 1)
        # Corriente MT: 34.8 / 37.5 ≈ 0.928 A
        assert resultado.fase_r.current_A == round(34.8 / 37.5, 2)
        # Potencia activa: invariante
        assert resultado.fase_r.net_active_power_W == 5000.0
