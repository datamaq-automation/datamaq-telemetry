# tests/unit/test_cargas_router.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.maquina_dto import (
    AnalisisConsumoResponseDTO,
    AtribucionConsumoResponseDTO,
    EnsayoResponseDTO,
    EstadisticaCiclosDTO,
    IntervaloActividadResponseDTO,
    MáquinaResponseDTO,
    PerfilConsumoResponseDTO,
    PerfilLineaBaseDTO,
)
from src.domain.maquinas.entities import IntervaloActividadMáquina
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    EstadoCampana,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    PatronOperacion,
    TipoCampana,
)
from src.infrastructure.fastapi.dependencies import (
    get_analisis_consumo_use_case,
    get_atribucion_use_case,
    get_caracterizacion_use_case,
    get_cargas_use_case,
    get_exportar_cargas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

MEDIDOR_ID = "d48c49f0-3564-4000-8000-000000000001"
AHORA = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _carga_response_dto(**kwargs) -> MáquinaResponseDTO:
    base = dict(
        id="maquina-1",
        dispositivo_id=MEDIDOR_ID,
        nombre="Compresor Principal",
        categoria=CategoriaCarga.OTROS,
        naturaleza_electrica=NaturalezaElectrica.MOTOR,
        patron_operacion=PatronOperacion.INDETERMINADO,
        potencia_nominal_w=15000.0,
        potencia_esperada_w=15000.0,
        firma=None,
        esta_caracterizada=False,
        activa=True,
        creado_en=AHORA,
        actualizado_en=AHORA,
    )
    base.update(kwargs)
    return MáquinaResponseDTO(**base)


def _campana_response_dto(**kwargs) -> EnsayoResponseDTO:
    base = dict(
        id="camp-1",
        dispositivo_id=MEDIDOR_ID,
        maquina_id="maquina-1",
        tipo=TipoCampana.ACTIVA,
        estado=EstadoCampana.EN_CURSO,
        inicio_at=AHORA,
        fin_planificado_at=AHORA,
        duracion_planificada_s=300.0,
        linea_base_W=None,
        linea_base_VAR=None,
        muestras=0,
        motivo_descarte=None,
        notas=None,
        rafaga_solicitada=True,
        resultado=None,
    )
    base.update(kwargs)
    return EnsayoResponseDTO(**base)


def _cliente(rol: str = "admin") -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "maquinas": MagicMock(),
        "analisis": MagicMock(),
        "atribucion": MagicMock(),
        "caracterizacion": MagicMock(),
        "exportar": MagicMock(),
    }
    app.dependency_overrides[get_cargas_use_case] = lambda: mocks["maquinas"]
    app.dependency_overrides[get_analisis_consumo_use_case] = lambda: mocks["analisis"]
    app.dependency_overrides[get_atribucion_use_case] = lambda: mocks["atribucion"]
    app.dependency_overrides[get_caracterizacion_use_case] = lambda: mocks["caracterizacion"]
    app.dependency_overrides[get_exportar_cargas_use_case] = lambda: mocks["exportar"]
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": rol}
    return TestClient(app), mocks


def test_listar_cargas_endpoint():
    client, mocks = _cliente()
    mocks["maquinas"].listar_cargas.return_value = [_carga_response_dto()]

    response = client.get(f"/api/v1/maquinas?device_id={MEDIDOR_ID}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "maquina-1"
    assert data[0]["nombre"] == "Compresor Principal"


def test_perfilar_consumo_endpoint():
    client, mocks = _cliente()
    mocks["analisis"].perfilar.return_value = PerfilConsumoResponseDTO(
        dispositivo_id=MEDIDOR_ID,
        desde=AHORA,
        hasta=AHORA,
        dias_analizados=14,
        zona_horaria="America/Argentina/Buenos_Aires",
        cantidad_lecturas=4032,
        linea_base=PerfilLineaBaseDTO(
            linea_base_W=360.0,
            linea_base_nocturna_W=110.0,
            linea_base_diurna_W=360.0,
            delta_diurno_W=250.0,
        ),
        ciclos_sobre_linea_base=EstadisticaCiclosDTO(
            ciclos=83,
            duracion_encendido_mediana_s=1500.0,
            duracion_apagado_mediana_s=3000.0,
            duty_cycle=0.35,
            patron=PatronOperacion.CICLICO_TERMOSTATICO,
            es_regular=True,
        ),
        umbral_ciclos_W=126.5,
        advertencia_cadencia=None,
    )

    response = client.get(f"/api/v1/maquinas/perfil?device_id={MEDIDOR_ID}&dias=14")
    assert response.status_code == 200
    data = response.json()
    assert data["dispositivo_id"] == MEDIDOR_ID
    assert data["linea_base"]["linea_base_W"] == 360.0


def test_obtener_atribucion_endpoint():
    client, mocks = _cliente()
    mocks["atribucion"].atribucion.return_value = AtribucionConsumoResponseDTO(
        dispositivo_id=MEDIDOR_ID,
        desde=AHORA,
        hasta=AHORA,
        energia_total_kwh=4500.0,
        energia_atribuida_kwh=3800.0,
        residual_kwh=700.0,
        residual_porcentaje=15.6,
        items=[],
        calidad_suficiente=True,
    )

    response = client.get(f"/api/v1/maquinas/atribucion?device_id={MEDIDOR_ID}&dias=30")
    assert response.status_code == 200
    data = response.json()
    assert data["energia_atribuida_kwh"] == 3800.0


def test_disparar_analisis_endpoint():
    client, mocks = _cliente()
    mocks["atribucion"].analizar.return_value = AnalisisConsumoResponseDTO(
        dispositivo_id=MEDIDOR_ID,
        desde=AHORA,
        hasta=AHORA,
        cantidad_lecturas=1000,
        episodios_detectados=15,
        intervalos_escritos=12,
        atribuidos=10,
        no_atribuidos=2,
    )

    response = client.post(f"/api/v1/maquinas/analisis?device_id={MEDIDOR_ID}&dias=7")
    assert response.status_code == 200
    data = response.json()
    assert data["episodios_detectados"] == 15


def test_corregir_intervalo_endpoint():
    client, mocks = _cliente()
    intervalo = IntervaloActividadMáquina(
        id=1,
        dispositivo_id=MEDIDOR_ID,
        maquina_id="maquina-1",
        inicio_at=AHORA,
        fin_at=AHORA,
        potencia_media_w=15000.0,
        origen=OrigenClasificacionCarga.CORRECCION_HUMANA,
        corregido_por_usuario_id="u1",
        corregido_at=AHORA,
        notas="Corrección manual",
    )
    mocks["atribucion"].corregir_intervalo.return_value = IntervaloActividadResponseDTO.model_validate(intervalo)

    payload = {"carga_id": "maquina-1", "notas": "Corrección manual"}
    response = client.patch("/api/v1/maquinas/intervalos/1/corregir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["origen"] == "CORRECCION_HUMANA"


def test_obtener_presets_catalogo_endpoint():
    client, _ = _cliente()
    response = client.get("/api/v1/maquinas/presets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_iniciar_campana_activa_endpoint():
    client, mocks = _cliente()
    mocks["caracterizacion"].iniciar_activa.return_value = _campana_response_dto()

    payload = {
        "dispositivo_id": MEDIDOR_ID,
        "carga_id": "maquina-1",
        "duracion_segundos": 300,
    }
    response = client.post("/api/v1/maquinas/campanas/activas", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "camp-1"


def test_finalizar_campana_endpoint():
    client, mocks = _cliente()
    mocks["caracterizacion"].finalizar.return_value = _campana_response_dto(
        estado=EstadoCampana.COMPLETADA, fin_at=AHORA
    )

    response = client.patch("/api/v1/maquinas/campanas/camp-1/finalizar")
    assert response.status_code == 200
    data = response.json()
    assert data["estado"] == "COMPLETADA"


def test_exportar_cargas_csv_endpoint():
    client, mocks = _cliente()
    mocks["exportar"].exportar_csv.return_value = iter([b"col1,col2\nval1,val2\n"])

    response = client.get(f"/api/v1/maquinas/exportar/csv?dispositivo_id={MEDIDOR_ID}&dias=30")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
