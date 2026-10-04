"""tests/integration/test_cargas_api.py — Pruebas de integración de la API de maquinas: registro de rutas, contrato y códigos de error."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.maquina_dto import (
    AnalisisConsumoResponseDTO,
    AtribucionConsumoResponseDTO,
    EnsayoResponseDTO,
    EstadisticaCiclosDTO,
    FirmaMáquinaDTO,
    IntervaloActividadResponseDTO,
    ItemAtribucionDTO,
    MáquinaResponseDTO,
    PerfilConsumoResponseDTO,
    PerfilLineaBaseDTO,
    ResultadoCalibracionDTO,
)
from src.domain.maquinas.exceptions import (
    EnsayoEnCursoError,
    MáquinaDuplicadaError,
    MáquinaNoEncontradaError,
)
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    NaturalezaElectrica,
    OrigenFirma,
    PatronOperacion,
)
from src.domain.maquinas.value_objects import (
    EstadoCampana as EstadoCampanaVO,
)
from src.domain.maquinas.value_objects import (
    MotivoDescarte as MotivoDescarteVO,
)
from src.domain.maquinas.value_objects import (
    OrigenClasificacionCarga as OrigenClasificacionCargaVO,
)
from src.domain.maquinas.value_objects import (
    PatronOperacion as PatronOperacionVO,
)
from src.domain.maquinas.value_objects import (
    TipoCampana as TipoCampanaVO,
)
from src.infrastructure.fastapi.dependencies import (
    get_analisis_consumo_use_case,
    get_atribucion_use_case,
    get_caracterizacion_use_case,
    get_cargas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

MEDIDOR_CASA = "d48c49f0-3564-4000-8000-000000000001"
AHORA = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _rutas_cargas(app) -> dict[str, set[str]]:
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())
    return {k: v for k, v in rutas.items() if k.startswith("/api/v1/maquinas")}


def _carga_dto(**kwargs) -> MáquinaResponseDTO:
    base = dict(
        id="maquina-1",
        dispositivo_id=MEDIDOR_CASA,
        nombre="Pava eléctrica",
        categoria=CategoriaCarga.COCCION,
        naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
        patron_operacion=PatronOperacion.INDETERMINADO,
        potencia_nominal_w=2000.0,
        potencia_esperada_w=2000.0,
        firma=None,
        esta_caracterizada=False,
        activa=True,
        creado_en=AHORA,
        actualizado_en=AHORA,
    )
    base.update(kwargs)
    return MáquinaResponseDTO(**base)


def _perfil_dto() -> PerfilConsumoResponseDTO:
    return PerfilConsumoResponseDTO(
        dispositivo_id=MEDIDOR_CASA,
        desde=AHORA,
        hasta=AHORA,
        dias_analizados=14,
        zona_horaria="America/Argentina/Buenos_Aires",
        cantidad_lecturas=4032,
        linea_base=PerfilLineaBaseDTO(
            linea_base_W=360.0, linea_base_nocturna_W=110.0, linea_base_diurna_W=360.0, delta_diurno_W=250.0
        ),
        ciclos_sobre_linea_base=EstadisticaCiclosDTO(
            ciclos=83,
            duracion_encendido_mediana_s=1500.0,
            duracion_apagado_mediana_s=3000.0,
            duty_cycle=0.35,
            patron=PatronOperacionVO.CICLICO_TERMOSTATICO,
            es_regular=True,
        ),
        umbral_ciclos_W=126.5,
        advertencia_cadencia="A una cadencia de 300 s, un encendido más corto no puede detectarse.",
    )


def _cliente(use_case: MagicMock, rol: str = "admin") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_cargas_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": rol}
    return TestClient(app)


def test_create_app_registra_rutas_de_cargas():
    rutas = _rutas_cargas(create_app())

    assert "GET" in rutas["/api/v1/maquinas"]
    assert "POST" in rutas["/api/v1/maquinas"]
    assert "GET" in rutas["/api/v1/maquinas/{carga_id}"]
    assert "PATCH" in rutas["/api/v1/maquinas/{carga_id}"]
    assert "PUT" in rutas["/api/v1/maquinas/{carga_id}/firma"]


def test_listar_cargas_filtra_por_dispositivo():
    use_case = MagicMock()
    use_case.listar_cargas.return_value = [_carga_dto()]

    resp = _cliente(use_case).get(f"/api/v1/maquinas?device_id={MEDIDOR_CASA}&solo_activas=true")

    assert resp.status_code == 200
    assert resp.json()[0]["nombre"] == "Pava eléctrica"
    use_case.listar_cargas.assert_called_once_with(dispositivo_id=MEDIDOR_CASA, solo_activas=True)


def test_registrar_carga_devuelve_el_contrato_completo():
    use_case = MagicMock()
    use_case.registrar_carga.return_value = _carga_dto()

    resp = _cliente(use_case).post(
        "/api/v1/maquinas",
        json={
            "nombre": "Pava eléctrica",
            "dispositivo_id": MEDIDOR_CASA,
            "categoria": "COCCION",
            "naturaleza_electrica": "RESISTIVA",
            "potencia_nominal_w": 2000.0,
        },
    )

    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["esta_caracterizada"] is False
    assert cuerpo["firma"] is None
    assert cuerpo["potencia_esperada_w"] == 2000.0
    assert cuerpo["creado_en"].endswith("Z")


def test_carga_inexistente_devuelve_404():
    use_case = MagicMock()
    use_case.obtener_carga.side_effect = MáquinaNoEncontradaError("Máquina 'x' no encontrada.")

    resp = _cliente(use_case).get("/api/v1/maquinas/x")

    assert resp.status_code == 404
    assert "no encontrada" in resp.json()["detail"]


def test_carga_duplicada_devuelve_422():
    use_case = MagicMock()
    use_case.registrar_carga.side_effect = MáquinaDuplicadaError("ya existe")

    resp = _cliente(use_case).post("/api/v1/maquinas", json={"nombre": "Heladera", "dispositivo_id": MEDIDOR_CASA})

    assert resp.status_code == 422
    assert resp.json()["detail"] == "ya existe"


def test_el_invitado_no_puede_registrar_cargas():
    use_case = MagicMock()

    resp = _cliente(use_case, rol="invitado").post(
        "/api/v1/maquinas", json={"nombre": "Heladera", "dispositivo_id": MEDIDOR_CASA}
    )

    assert resp.status_code == 403
    use_case.registrar_carga.assert_not_called()


def test_fijar_firma_manual_expone_origen_y_completitud():
    use_case = MagicMock()
    use_case.fijar_firma_manual.return_value = _carga_dto(
        esta_caracterizada=True,
        potencia_esperada_w=1850.0,
        firma=FirmaMáquinaDTO(
            potencia_w=1850.0,
            dispersion_w=90.0,
            factor_potencia=0.99,
            duracion_encendido_s=180.0,
            origen=OrigenFirma.CHAPA,
            es_resistiva=True,
            esta_completa=True,
        ),
    )

    resp = _cliente(use_case).put(
        "/api/v1/maquinas/maquina-1/firma",
        json={"potencia_w": 1850.0, "dispersion_w": 90.0, "factor_potencia": 0.99, "duracion_encendido_s": 180.0},
    )

    assert resp.status_code == 200
    firma = resp.json()["firma"]
    assert firma["origen"] == "CHAPA"
    assert firma["esta_completa"] is True


def test_potencia_nominal_no_positiva_es_rechazada_por_el_contrato():
    use_case = MagicMock()

    resp = _cliente(use_case).post(
        "/api/v1/maquinas",
        json={"nombre": "Heladera", "dispositivo_id": MEDIDOR_CASA, "potencia_nominal_w": 0},
    )

    assert resp.status_code == 422
    use_case.registrar_carga.assert_not_called()


def test_create_app_registra_la_ruta_de_perfil():
    rutas = _rutas_cargas(create_app())

    assert "GET" in rutas["/api/v1/maquinas/perfil"]


def test_perfil_no_se_confunde_con_el_id_de_una_carga():
    """`/perfil` está declarada antes que `/{carga_id}`: no debe caer en el CRUD."""
    maquinas = MagicMock()
    analisis = MagicMock()
    analisis.perfilar.return_value = _perfil_dto()

    app = create_app()
    app.dependency_overrides[get_cargas_use_case] = lambda: maquinas
    app.dependency_overrides[get_analisis_consumo_use_case] = lambda: analisis
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin"}

    resp = TestClient(app).get(f"/api/v1/maquinas/perfil?device_id={MEDIDOR_CASA}&dias=7")

    assert resp.status_code == 200
    maquinas.obtener_carga.assert_not_called()
    analisis.perfilar.assert_called_once_with(MEDIDOR_CASA, dias=7, zona="America/Argentina/Buenos_Aires")


def test_el_perfil_expone_linea_base_ciclos_y_advertencia_de_cadencia():
    analisis = MagicMock()
    analisis.perfilar.return_value = _perfil_dto()

    app = create_app()
    app.dependency_overrides[get_analisis_consumo_use_case] = lambda: analisis
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin"}

    cuerpo = TestClient(app).get(f"/api/v1/maquinas/perfil?device_id={MEDIDOR_CASA}").json()

    assert cuerpo["linea_base"]["linea_base_nocturna_W"] == 110.0
    assert cuerpo["ciclos_sobre_linea_base"]["patron"] == "CICLICO_TERMOSTATICO"
    assert cuerpo["ciclos_sobre_linea_base"]["duty_cycle"] == 0.35
    assert "no puede" in cuerpo["advertencia_cadencia"]


def test_el_invitado_puede_leer_el_perfil():
    """El perfil es lectura: no requiere rol de escritura."""
    analisis = MagicMock()
    analisis.perfilar.return_value = _perfil_dto()

    app = create_app()
    app.dependency_overrides[get_analisis_consumo_use_case] = lambda: analisis
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "invitado"}

    assert TestClient(app).get(f"/api/v1/maquinas/perfil?device_id={MEDIDOR_CASA}").status_code == 200


def _campana_dto(**kwargs) -> EnsayoResponseDTO:
    base = dict(
        id="camp-1",
        dispositivo_id=MEDIDOR_CASA,
        maquina_id="maquina-1",
        tipo=TipoCampanaVO.ACTIVA,
        estado=EstadoCampanaVO.EN_CURSO,
        inicio_at=AHORA,
        fin_planificado_at=AHORA,
        duracion_planificada_s=300.0,
        rafaga_solicitada=True,
    )
    base.update(kwargs)
    return EnsayoResponseDTO(**base)


def _cliente_campanas(use_case: MagicMock, rol: str = "admin") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_caracterizacion_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": rol}
    return TestClient(app)


def test_create_app_registra_las_rutas_de_campana():
    rutas = _rutas_cargas(create_app())

    assert "POST" in rutas["/api/v1/maquinas/campanas/activas"]
    assert "POST" in rutas["/api/v1/maquinas/campanas/pasivas"]
    assert "GET" in rutas["/api/v1/maquinas/campanas/{campana_id}"]
    assert "PATCH" in rutas["/api/v1/maquinas/campanas/{campana_id}/finalizar"]
    assert "PATCH" in rutas["/api/v1/maquinas/campanas/{campana_id}/descartar"]
    assert "GET" in rutas["/api/v1/maquinas/{carga_id}/campanas"]


def test_iniciar_campana_activa_informa_si_la_rafaga_se_pidio():
    use_case = MagicMock()
    use_case.iniciar_activa.return_value = _campana_dto()

    resp = _cliente_campanas(use_case).post(
        "/api/v1/maquinas/campanas/activas",
        json={"dispositivo_id": MEDIDOR_CASA, "duracion_segundos": 300, "carga_id": "maquina-1"},
    )

    assert resp.status_code == 200
    assert resp.json()["rafaga_solicitada"] is True
    assert use_case.iniciar_activa.call_args.kwargs["usuario_id"] == "u1"


def test_la_ruta_de_campana_no_colisiona_con_la_de_una_carga():
    """`/campanas/{id}` y `/{carga_id}/campanas` tienen la misma forma: importa el orden."""
    maquinas, campanas = MagicMock(), MagicMock()
    campanas.obtener.return_value = _campana_dto()
    campanas.listar_por_carga.return_value = [_campana_dto()]

    app = create_app()
    app.dependency_overrides[get_cargas_use_case] = lambda: maquinas
    app.dependency_overrides[get_caracterizacion_use_case] = lambda: campanas
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "admin"}
    cliente = TestClient(app)

    assert cliente.get("/api/v1/maquinas/campanas/camp-1").status_code == 200
    assert cliente.get("/api/v1/maquinas/maquina-1/campanas").status_code == 200
    campanas.obtener.assert_called_once_with("camp-1")
    campanas.listar_por_carga.assert_called_once_with("maquina-1")
    maquinas.obtener_carga.assert_not_called()


def test_finalizar_una_campana_contaminada_devuelve_200_con_el_motivo():
    """No es un error del servidor: es el resultado honesto de una medición sucia."""
    use_case = MagicMock()
    use_case.finalizar.return_value = _campana_dto(
        estado=EstadoCampanaVO.CONTAMINADA,
        motivo_descarte=MotivoDescarteVO.ESCALON_AJENO,
        notas="Apareció un escalón de 2000 W dentro de la ventana: otra maquina entró.",
        resultado=ResultadoCalibracionDTO(
            estado=EstadoCampanaVO.CONTAMINADA,
            motivo=MotivoDescarteVO.ESCALON_AJENO,
            detalle="otra maquina entró en medio de la medición",
        ),
    )

    cuerpo = _cliente_campanas(use_case).patch("/api/v1/maquinas/campanas/camp-1/finalizar").json()

    assert cuerpo["estado"] == "CONTAMINADA"
    assert cuerpo["motivo_descarte"] == "ESCALON_AJENO"
    assert cuerpo["resultado"]["firma"] is None


def test_no_se_puede_abrir_una_segunda_campana_sobre_el_mismo_medidor():
    use_case = MagicMock()
    use_case.iniciar_activa.side_effect = EnsayoEnCursoError("ya hay una campaña en curso")

    resp = _cliente_campanas(use_case).post(
        "/api/v1/maquinas/campanas/activas",
        json={"dispositivo_id": MEDIDOR_CASA, "duracion_segundos": 300},
    )

    assert resp.status_code == 422


def test_una_duracion_desmedida_es_rechazada_por_el_contrato():
    """Seis horas es el tope: una campaña más larga es una cadencia permanente encubierta."""
    use_case = MagicMock()

    resp = _cliente_campanas(use_case).post(
        "/api/v1/maquinas/campanas/pasivas",
        json={"dispositivo_id": MEDIDOR_CASA, "duracion_segundos": 90_000},
    )

    assert resp.status_code == 422
    use_case.iniciar_pasiva.assert_not_called()


def test_el_invitado_no_puede_abrir_campanas():
    use_case = MagicMock()

    resp = _cliente_campanas(use_case, rol="invitado").post(
        "/api/v1/maquinas/campanas/activas",
        json={"dispositivo_id": MEDIDOR_CASA, "duracion_segundos": 300},
    )

    assert resp.status_code == 403
    use_case.iniciar_activa.assert_not_called()


def _cliente_atribucion(use_case: MagicMock, rol: str = "admin") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_atribucion_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": rol}
    return TestClient(app)


def test_create_app_registra_las_rutas_de_atribucion():
    rutas = _rutas_cargas(create_app())

    assert "GET" in rutas["/api/v1/maquinas/atribucion"]
    assert "POST" in rutas["/api/v1/maquinas/analisis"]
    assert "PATCH" in rutas["/api/v1/maquinas/intervalos/{intervalo_id}/corregir"]
    assert "GET" in rutas["/api/v1/maquinas/{carga_id}/intervalos"]


def test_la_atribucion_expone_el_residual_como_dato_de_primera_clase():
    """A esta cadencia siempre habrá consumo sin explicar; ocultarlo sería mentir."""
    use_case = MagicMock()
    use_case.atribucion.return_value = AtribucionConsumoResponseDTO(
        dispositivo_id=MEDIDOR_CASA,
        desde=AHORA,
        hasta=AHORA,
        energia_total_kwh=120.0,
        energia_atribuida_kwh=68.0,
        residual_kwh=52.0,
        residual_porcentaje=0.4333,
        items=[
            ItemAtribucionDTO(maquina_id="c1", nombre="Termotanque", energia_kwh=48.0, porcentaje=0.4, intervalos=30),
            ItemAtribucionDTO(maquina_id=None, nombre="No atribuido", energia_kwh=52.0, porcentaje=0.43, intervalos=0),
        ],
        calidad_suficiente=False,
        advertencia="Queda sin atribuir el 43% del consumo.",
    )

    cuerpo = _cliente_atribucion(use_case).get(f"/api/v1/maquinas/atribucion?device_id={MEDIDOR_CASA}").json()

    assert cuerpo["residual_kwh"] == 52.0
    assert cuerpo["calidad_suficiente"] is False
    assert any(i["carga_id"] is None and i["nombre"] == "No atribuido" for i in cuerpo["items"])


def test_disparar_el_analisis_devuelve_el_recuento_de_atribuidos():
    use_case = MagicMock()
    use_case.analizar.return_value = AnalisisConsumoResponseDTO(
        dispositivo_id=MEDIDOR_CASA,
        desde=AHORA,
        hasta=AHORA,
        cantidad_lecturas=2016,
        umbral_escalon_W=180.0,
        episodios_detectados=42,
        intervalos_escritos=42,
        atribuidos=31,
        no_atribuidos=11,
        cargas_con_firma=5,
    )

    cuerpo = _cliente_atribucion(use_case).post(f"/api/v1/maquinas/analisis?device_id={MEDIDOR_CASA}&dias=7").json()

    assert cuerpo["atribuidos"] == 31
    assert cuerpo["no_atribuidos"] == 11
    use_case.analizar.assert_called_once_with(MEDIDOR_CASA, dias=7)


def test_corregir_un_intervalo_registra_al_usuario():
    use_case = MagicMock()
    use_case.corregir_intervalo.return_value = IntervaloActividadResponseDTO(
        id=7,
        dispositivo_id=MEDIDOR_CASA,
        maquina_id="c1",
        inicio_at=AHORA,
        fin_at=AHORA,
        duracion_segundos=2400.0,
        origen=OrigenClasificacionCargaVO.CORRECCION_HUMANA,
        esta_atribuido=True,
        corregido_por_usuario_id="u1",
    )

    resp = _cliente_atribucion(use_case).patch(
        "/api/v1/maquinas/intervalos/7/corregir", json={"carga_id": "c1", "notas": "fui yo"}
    )

    assert resp.status_code == 200
    assert resp.json()["origen"] == "CORRECCION_HUMANA"
    assert use_case.corregir_intervalo.call_args.kwargs["usuario_id"] == "u1"


def test_el_invitado_no_puede_corregir_ni_disparar_el_analisis():
    use_case = MagicMock()
    cliente = _cliente_atribucion(use_case, rol="invitado")

    assert cliente.post(f"/api/v1/maquinas/analisis?device_id={MEDIDOR_CASA}").status_code == 403
    assert cliente.patch("/api/v1/maquinas/intervalos/7/corregir", json={"carga_id": None}).status_code == 403
    use_case.analizar.assert_not_called()
    use_case.corregir_intervalo.assert_not_called()


def test_el_invitado_si_puede_leer_la_atribucion():
    use_case = MagicMock()
    use_case.atribucion.return_value = AtribucionConsumoResponseDTO(
        dispositivo_id=MEDIDOR_CASA, desde=AHORA, hasta=AHORA
    )

    resp = _cliente_atribucion(use_case, rol="invitado").get(f"/api/v1/maquinas/atribucion?device_id={MEDIDOR_CASA}")

    assert resp.status_code == 200
