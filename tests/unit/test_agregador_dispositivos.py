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
