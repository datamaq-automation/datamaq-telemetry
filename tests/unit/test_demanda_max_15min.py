"""tests/unit/test_demanda_max_15min.py — pico (demanda_max) y promedio por bloque de 15 min.

Cubre la serie de potencia con granularidad 15m: el promedio por bloque ya existía; estos tests fijan
el máximo de muestras dentro del bloque (`demanda_max_w` / `demanda_max_kw`) y el promedio en kW.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.telemetria_dto import (
    HistoricoInstantaneasDTO,
    LecturaInstantaneaDTO,
    MedicionFaseDTO,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.agregador_dispositivos import AgregadorDispositivosService
from src.domain.telemetria.servicios.agregador_lecturas import AgregadorLecturasService
from src.domain.telemetria.value_objects import PotenciaActiva
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_exportar_telemetria_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.server import create_app

INICIO = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)  # 12:00 UTC: inicio de bloque de 15 min
BLOQUE_15M = 900
DEV_ID = "d48c49f0-3564-4000-8000-000000000001"
DATOS_DESDE = datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc)


def _t(segundos: int) -> datetime:
    return INICIO + timedelta(seconds=segundos)


# ==============================================================================
# Dominio: agregación de varios medidores por bloque
# ==============================================================================


class TestPicoPorBloqueMultiMedidor:
    def test_pico_de_la_suma_alineada_supera_al_promedio(self):
        # Medidores desincronizados dentro del mismo bloque de 15 min:
        #   A: 1000 W a t=0 y 3000 W a t=600
        #   B: 2000 W a t=300
        # Suma con la última muestra conocida de cada medidor: t=0 → 1000; t=300 → 3000; t=600 → 5000.
        # Promedio del bloque (promedio por medidor, luego suma): A=2000 + B=2000 = 4000.
        lecturas = {
            "A": [(_t(0), 1000.0), (_t(600), 3000.0)],
            "B": [(_t(300), 2000.0)],
        }
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, BLOQUE_15M)

        assert len(puntos) == 1
        assert puntos[0].potencia_activa_total_w == 4000.0
        assert puntos[0].demanda_max_w == 5000.0

    def test_pico_no_arrastra_valores_de_un_bloque_anterior(self):
        # C tiene una muestra alta en el bloque 0 (9000 W) y nada en el bloque siguiente.
        # En el bloque 1 solo reporta A (1000 W): el pico debe ser 1000, no 10000.
        lecturas = {
            "A": [(_t(1000), 1000.0)],
            "C": [(_t(100), 9000.0)],
        }
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, BLOQUE_15M)

        pico_por_inicio = {p.momento: p.demanda_max_w for p in puntos}
        assert pico_por_inicio[_t(0)] == 9000.0
        assert pico_por_inicio[_t(900)] == 1000.0

    def test_un_solo_medidor_con_una_muestra_pico_igual_al_promedio(self):
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo({"A": [(_t(10), 2500.0)]}, BLOQUE_15M)

        assert puntos[0].potencia_activa_total_w == 2500.0
        assert puntos[0].demanda_max_w == 2500.0

    def test_muestras_sin_potencia_no_generan_pico(self):
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo({"A": [(_t(10), None)]}, BLOQUE_15M)

        assert puntos[0].potencia_activa_total_w is None
        assert puntos[0].demanda_max_w is None


# ==============================================================================
# Dominio: agregación de lecturas instantáneas de un medidor (/instantaneous)
# ==============================================================================


def _lectura(segundos: int, vatios: float | None) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=DEV_ID,
        registrado_en=_t(segundos),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios) if vatios is not None else None,
    )


class TestPicoEnAgregadorDeInstantaneas:
    def test_bloque_agregado_guarda_el_maximo_de_sus_muestras(self):
        lecturas = [_lectura(0, 1000.0), _lectura(300, 3000.0), _lectura(600, 2000.0)]
        agregadas = AgregadorLecturasService.agregar_lecturas_en_intervalo(lecturas, BLOQUE_15M)

        assert len(agregadas) == 1
        assert agregadas[0].potencia_activa_total.vatios == 2000.0  # promedio del bloque
        assert agregadas[0].demanda_max_w == 3000.0  # pico de muestras

    def test_muestras_sin_potencia_se_ignoran_en_el_pico(self):
        lecturas = [_lectura(0, None), _lectura(300, 1500.0)]
        agregadas = AgregadorLecturasService.agregar_lecturas_en_intervalo(lecturas, BLOQUE_15M)

        assert agregadas[0].demanda_max_w == 1500.0

    def test_lectura_cruda_no_tiene_pico(self):
        assert _lectura(0, 1000.0).demanda_max_w is None


# ==============================================================================
# Mapper y endpoint: contrato aditivo de la respuesta
# ==============================================================================


def _medicion_fase_dto() -> MedicionFaseDTO:
    return MedicionFaseDTO(voltage_V=220.0, current_A=10.0, net_active_power_W=2200.0)


def _lectura_dto(**kwargs) -> LecturaInstantaneaDTO:
    base = dict(
        id=1,
        dispositivo_id=DEV_ID,
        registrado_en=INICIO,
        fase_r=_medicion_fase_dto(),
        fase_s=_medicion_fase_dto(),
        fase_t=_medicion_fase_dto(),
        potencia_activa_total_W=2000.0,
    )
    base.update(kwargs)
    return LecturaInstantaneaDTO(**base)


class TestMapperDemandaMax:
    def test_bloque_agregado_expone_promedio_y_pico_en_kw(self):
        bloque = LecturaInstantanea(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=INICIO,
            fase_r=MedicionFase(),
            fase_s=MedicionFase(),
            fase_t=MedicionFase(),
            potencia_activa_total=PotenciaActiva(2000.0),
            demanda_max_w=3500.0,
        )
        dto = TelemetriaMapper.instantanea_to_dto(bloque, analitica=None, dispositivo=None)

        assert dto.promedio_kw == 2.0
        assert dto.demanda_max_kw == 3.5

    def test_lectura_cruda_deja_los_campos_en_none(self):
        bloque = LecturaInstantanea(
            id=None,
            dispositivo_id=DEV_ID,
            registrado_en=INICIO,
            fase_r=MedicionFase(),
            fase_s=MedicionFase(),
            fase_t=MedicionFase(),
            potencia_activa_total=PotenciaActiva(2000.0),
        )
        dto = TelemetriaMapper.instantanea_to_dto(bloque, analitica=None, dispositivo=None)

        assert dto.promedio_kw is None
        assert dto.demanda_max_kw is None


def _cliente_instantaneas(historico: HistoricoInstantaneasDTO) -> TestClient:
    app = create_app()
    telemetria = MagicMock()
    telemetria.historico_instantaneas.return_value = historico
    telemetria.datos_desde.return_value = DATOS_DESDE
    app.dependency_overrides[get_telemetria_use_case] = lambda: telemetria
    app.dependency_overrides[get_alertas_use_case] = lambda: MagicMock()
    app.dependency_overrides[get_exportar_telemetria_use_case] = lambda: MagicMock()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin", "org": "org-1"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    return TestClient(app)


class TestEndpointInstantaneasDemandaMax:
    def test_respuesta_incluye_promedio_y_pico_en_bloques_agregados(self):
        client = _cliente_instantaneas(
            HistoricoInstantaneasDTO(
                lecturas=[_lectura_dto(potencia_activa_total_W=2000.0, promedio_kw=2.0, demanda_max_kw=3.5)],
                datos_desde=DATOS_DESDE,
            )
        )
        response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?granularity=15m&hours=24")

        assert response.status_code == 200
        dato = response.json()[0]
        assert dato["promedio_kw"] == 2.0
        assert dato["demanda_max_kw"] == 3.5
        # Contrato existente intacto
        assert dato["potencia_activa_total_W"] == 2000.0

    def test_respuesta_sin_bloque_agregado_mantiene_campos_nulos(self):
        client = _cliente_instantaneas(HistoricoInstantaneasDTO(lecturas=[_lectura_dto()], datos_desde=DATOS_DESDE))
        response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?granularity=raw")

        dato = response.json()[0]
        assert dato["promedio_kw"] is None
        assert dato["demanda_max_kw"] is None
