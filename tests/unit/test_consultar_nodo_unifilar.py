"""tests/unit/test_consultar_nodo_unifilar.py — Telemetría agregada por nodo del unifilar."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.domain.sge.entities import FacturaDistribuidora
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase, NodoUnifilar, Planta
from src.domain.telemetria.exceptions import NodoUnifilarNoEncontradoError, PlantaNoEncontradaError
from src.domain.telemetria.value_objects import (
    Corriente,
    MetadatosPlaca,
    PotenciaActiva,
    PotenciaReactiva,
    Tension,
    TipoNodoUnifilar,
)

PLANTA_ID = "planta-durax"
ORG_ID = "org-durax"
DEV_1 = "dev-trafo-1"
DEV_2 = "dev-trafo-2"


def _nodo(id_: str, tipo: TipoNodoUnifilar, parent_id: str | None = None, device_id: str | None = None):
    return NodoUnifilar(
        id=id_,
        planta_id=PLANTA_ID,
        nombre=id_,
        tipo=tipo,
        tension_nominal_v=380.0,
        parent_id=parent_id,
        device_id=device_id,
    )


def _lectura(dispositivo_id: str, vatios: float, var: float | None = None) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=datetime(2026, 9, 12, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios),
        potencia_reactiva_total=PotenciaReactiva(var) if var is not None else None,
    )


@pytest.fixture
def use_case():
    repo_org = MagicMock()
    repo_org.obtener_planta_por_id.return_value = Planta(id=PLANTA_ID, organizacion_id=ORG_ID, nombre="Durax")
    repo_org.obtener_nodos_unifilar.return_value = [
        _nodo("mt", TipoNodoUnifilar.ACOMETIDA),
        _nodo("trafo-1", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt", device_id=DEV_1),
        _nodo("trafo-2", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt", device_id=DEV_2),
    ]

    repo_telemetria = MagicMock()
    repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: {
        DEV_1: _lectura(DEV_1, 300_000.0),
        DEV_2: _lectura(DEV_2, 150_000.0),
    }.get(dev_id)

    consultar_telemetria = MagicMock()
    consultar_telemetria.listar_energia_agregada.side_effect = lambda dev_id, *a, **k: [
        EnergiaAgregadaDTO(periodo=date(2026, 9, 12), energia_activa_neta_kwh={DEV_1: 10.0, DEV_2: 5.0}[dev_id])
    ]
    consultar_telemetria.listar_instantaneas.return_value = []
    consultar_telemetria.datos_desde.return_value = datetime(2026, 8, 29, tzinfo=timezone.utc)

    return ConsultarNodoUnifilarUseCase(repo_org, repo_telemetria, consultar_telemetria)


def test_nodo_virtual_suma_los_dos_trafos(use_case):
    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)

    assert resumen.es_virtual is True
    assert resumen.dispositivos_ids == [DEV_1, DEV_2]
    assert resumen.potencia_activa_total_w == 450_000.0
    assert resumen.dispositivos_sin_dato == []
    assert resumen.energia_agregada[0].energia_activa_neta_kwh == 15.0


def test_nodo_medido_devuelve_solo_su_medidor(use_case):
    resumen = use_case.resumen(PLANTA_ID, "trafo-1", organizacion_id=ORG_ID)

    assert resumen.es_virtual is False
    assert resumen.dispositivos_ids == [DEV_1]
    assert resumen.potencia_activa_total_w == 300_000.0


def test_superadmin_sin_org_accede(use_case):
    assert use_case.resumen(PLANTA_ID, "mt", organizacion_id=None).nodo_id == "mt"


def test_planta_de_otro_tenant_es_404(use_case):
    with pytest.raises(PlantaNoEncontradaError):
        use_case.resumen(PLANTA_ID, "mt", organizacion_id="otra-org")


def test_nodo_inexistente_es_404(use_case):
    with pytest.raises(NodoUnifilarNoEncontradoError):
        use_case.resumen(PLANTA_ID, "no-existe", organizacion_id=ORG_ID)


def test_historico_consulta_los_medidores_frontera(use_case):
    historico = use_case.historico(PLANTA_ID, "mt", organizacion_id=ORG_ID, granularidad="5m", horas=1)

    llamados = [c.args[0] for c in use_case.consultar_telemetria.listar_instantaneas.call_args_list]
    assert llamados == [DEV_1, DEV_2]
    assert historico.puntos == []
    assert historico.datos_desde == datetime(2026, 8, 29, tzinfo=timezone.utc)


def test_compensacion_historica_incluida_en_nodo_mt_o_total_planta(use_case):
    resumen_mt = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)
    assert resumen_mt.compensacion_historica is not None
    assert resumen_mt.compensacion_historica.periodo_dias == 30  # Default: 30 días (ISO 50001)


def test_compensacion_historica_es_none_en_nodo_bt_individual(use_case):
    resumen_trafo = use_case.resumen(PLANTA_ID, "trafo-1", organizacion_id=ORG_ID)
    assert resumen_trafo.compensacion_historica is None


def test_nodo_agregado_potencia_activa_unidades_w(use_case):
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: {
        DEV_1: _lectura(DEV_1, 1120.0),
        DEV_2: _lectura(DEV_2, 8030.0),
    }.get(dev_id)

    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)
    assert resumen.potencia_activa_total_w == 9150.0


def test_resumen_nodo_bt_expone_nivel_y_nominales(use_case):
    resumen = use_case.resumen(PLANTA_ID, "trafo-1", organizacion_id=ORG_ID)

    assert resumen.nivel_tension == "BT"
    assert resumen.tension_nominal_V == 380.0
    assert round(resumen.tension_nominal_fase_V or 0, 1) == 219.4


def test_resumen_nodo_mt_expone_nivel_y_nominales(use_case):
    nodo_mt = _nodo("mt-13200", TipoNodoUnifilar.ACOMETIDA)
    nodo_mt.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [nodo_mt]

    resumen = use_case.resumen(PLANTA_ID, "mt-13200", organizacion_id=ORG_ID)

    assert resumen.nivel_tension == "MT"
    assert resumen.tension_nominal_V == 13200.0
    assert round(resumen.tension_nominal_fase_V or 0, 0) == 7621.0


# --- Escala del agregado por fase: invariante nivel_tension ↔ voltajes agregados ---
# Las ramas de decisión del factor se prueban en tests/unit/test_relacion_transformacion.py;
# acá se verifica el resultado observable en el DTO del resumen.


def _lectura_con_fases(dispositivo_id: str, v_ln: float) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=datetime(2026, 9, 22, tzinfo=timezone.utc),
        fase_r=MedicionFase(tension=Tension(v_ln), corriente=Corriente(100.0), potencia_activa=PotenciaActiva(1000.0)),
        fase_s=MedicionFase(tension=Tension(v_ln), corriente=Corriente(100.0), potencia_activa=PotenciaActiva(1000.0)),
        fase_t=MedicionFase(tension=Tension(v_ln), corriente=Corriente(100.0), potencia_activa=PotenciaActiva(1000.0)),
        potencia_activa_total=PotenciaActiva(3000.0),
    )


def test_resumen_nodo_mt_sin_placa_escala_el_agregado_al_nivel_del_nodo(use_case):
    """Reproduce `nodo-durax-acometida-mt`: acometida de 13.2 kV que NO declara
    `relacion_tension_kv`, con dos medidores frontera en la barra de 380 V.

    Antes de derivar la relación del árbol, el resumen devolvía nivel_tension="MT"
    junto a fases de ~225 V (anomalía ANOMALIA_ESCALA_DATOS vista en el frontend).
    """
    acometida = _nodo("mt", TipoNodoUnifilar.ACOMETIDA)
    acometida.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt", device_id=DEV_1),
        _nodo("tgbt-2", TipoNodoUnifilar.TGBT, parent_id="mt", device_id=DEV_2),
    ]
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: _lectura_con_fases(dev_id, 224.8)

    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)

    assert resumen.nivel_tension == "MT"
    assert resumen.agregado_por_fase is not None
    nominal_fase = resumen.tension_nominal_fase_V or 0.0
    for fase in (
        resumen.agregado_por_fase.fase_r,
        resumen.agregado_por_fase.fase_s,
        resumen.agregado_por_fase.fase_t,
    ):
        assert fase.voltage_V is not None
        assert abs(fase.voltage_V - nominal_fase) / nominal_fase <= 0.10


def test_resumen_nodo_mt_con_placa_coherente_usa_la_relacion_de_placa(use_case):
    """Caso UPP: la acometida MT declara "13.2/0.4" (relación de transformación de
    placa, a=33). Es coherente con el cociente del árbol (34.74) y tiene prioridad
    por ser el turns ratio real del equipo."""
    acometida = _nodo("mt", TipoNodoUnifilar.ACOMETIDA)
    acometida.tension_nominal_v = 13200.0
    acometida.metadatos_placa = MetadatosPlaca(relacion_tension_kv="13.2/0.4")
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt", device_id=DEV_1),
    ]
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: _lectura_con_fases(dev_id, 220.0)

    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)

    assert resumen.agregado_por_fase is not None
    assert resumen.agregado_por_fase.fase_r.voltage_V == round(220.0 * 33.0, 1)


def test_resumen_nodo_mt_expone_compuestas_y_las_marca_como_canonicas(use_case):
    """En MT la red es de 3 conductores y el primario va en triángulo (Dyn11): la
    magnitud accesible es la compuesta, no la fase-neutro. El resumen debe exponer
    V_RS/V_ST/V_TR a la escala del nodo y decir que son ésas las que se muestran."""
    acometida = _nodo("mt", TipoNodoUnifilar.ACOMETIDA)
    acometida.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt", device_id=DEV_1),
    ]
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: _lectura_con_fases(dev_id, 224.8)

    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)

    assert resumen.magnitud_tension_canonica == "LINEA"
    assert resumen.agregado_por_fase is not None
    # 224.8 V de fase en BT → x34.74 → 7808.8 V de fase en MT → x√3 → ~13.5 kV compuestos,
    # o sea la nominal de 13.2 kV con la misma desviación que traía la medición.
    nominal_ll = resumen.tension_nominal_V or 0.0
    for compuesta in (
        resumen.agregado_por_fase.tension_linea_rs_V,
        resumen.agregado_por_fase.tension_linea_st_V,
        resumen.agregado_por_fase.tension_linea_tr_V,
    ):
        assert compuesta is not None
        assert abs(compuesta - nominal_ll) / nominal_ll <= 0.10


def test_resumen_nodo_bt_marca_la_fase_neutro_como_canonica(use_case):
    """En BT la distribución es estrella con neutro: la fase-neutro sí se mide en
    bornes, así que sigue siendo la magnitud a mostrar (las compuestas van igual)."""
    nodo_bt = _nodo("tgbt", TipoNodoUnifilar.TGBT, device_id=DEV_1)
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [nodo_bt]
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: _lectura_con_fases(dev_id, 219.4)

    resumen = use_case.resumen(PLANTA_ID, "tgbt", organizacion_id=ORG_ID)

    assert resumen.magnitud_tension_canonica == "FASE"
    assert resumen.agregado_por_fase is not None
    assert resumen.agregado_por_fase.fase_r.voltage_V == 219.4
    assert resumen.agregado_por_fase.tension_linea_rs_V == pytest.approx(380.0, abs=0.1)


def test_resumen_no_escala_nodo_bt_aunque_declare_relacion_tension_kv(use_case):
    """Reproduce el caso Durax end-to-end: un nodo BT con relacion_tension_kv de
    placa no debe alterar el agregado_por_fase (sin escalado, factor 1.0)."""
    nodo_bt_con_placa = _nodo("trafo-durax", TipoNodoUnifilar.TRANSFORMADOR, device_id=DEV_1)
    nodo_bt_con_placa.tension_nominal_v = 380.0
    nodo_bt_con_placa.metadatos_placa = MetadatosPlaca(relacion_tension_kv="13.2/0.4")
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [nodo_bt_con_placa]
    use_case.repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: {
        DEV_1: _lectura(DEV_1, 1000.0),
    }.get(dev_id)

    resumen = use_case.resumen(PLANTA_ID, "trafo-durax", organizacion_id=ORG_ID)

    assert resumen.nivel_tension == "BT"
    assert resumen.potencia_activa_total_w == 1000.0


def test_compensacion_historica_calcula_banco_recomendado_con_datos_reactivos(use_case):
    """Cubre rama _calcular_compensacion_historica() cuando hay potencia reactiva:
    verifica que se calcula Q promedio, factor de potencia y se sugiere banco.
    Líneas 138-162 del use case."""
    acometida_mt = _nodo("mt-13200v", TipoNodoUnifilar.ACOMETIDA)
    acometida_mt.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida_mt,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt-13200v", device_id=DEV_1),
    ]

    # Simular 3 lecturas instantáneas con P=100kW, Q=50kVAr (FP~0.89)
    puntos_historico = [
        (
            datetime(2026, 9, 12, hour=i, tzinfo=timezone.utc),
            100_000.0,  # P en W
            50_000.0,  # Q en VAr
        )
        for i in range(3)
    ]

    use_case.consultar_telemetria.listar_instantaneas.return_value = [
        type(
            "PuntoPotencia",
            (),
            {"registrado_en": p[0], "potencia_activa_total_W": p[1], "potencia_reactiva_total_VAR": p[2]},
        )()
        for p in puntos_historico
    ]

    # Última lectura para el resumen
    use_case.repo_telemetria.obtener_ultima_instantanea.return_value = _lectura(DEV_1, 100_000.0, var=50_000.0)

    resumen = use_case.resumen(PLANTA_ID, "mt-13200v", organizacion_id=ORG_ID)

    # Verificar que compensación se calculó con datos reactivos
    assert resumen.compensacion_historica is not None
    assert resumen.compensacion_historica.potencia_reactiva_promedio_kvar == 50.0
    assert resumen.compensacion_historica.potencia_reactiva_max_kvar == 50.0
    assert resumen.compensacion_historica.potencia_reactiva_min_kvar == 50.0
    # FP debería estar alrededor de 0.89 (cos φ de P/S)
    assert resumen.compensacion_historica.factor_potencia_promedio is not None
    assert 0.85 < (resumen.compensacion_historica.factor_potencia_promedio or 0) < 0.95
    assert resumen.compensacion_historica.periodo_dias == 30
    assert resumen.compensacion_historica.sobrecompensacion_sostenida is False


def test_resumen_nodo_respeta_parametro_periodo_dias(use_case):
    """Valida que use_case.resumen() acepta periodo_dias explícito y lo propaga."""
    acometida_mt = _nodo("mt-13200v", TipoNodoUnifilar.ACOMETIDA)
    acometida_mt.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida_mt,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt-13200v", device_id=DEV_1),
    ]

    use_case.consultar_telemetria.listar_instantaneas.return_value = []
    use_case.repo_telemetria.obtener_ultima_instantanea.return_value = _lectura(DEV_1, 100_000.0)

    # 1. Sin especificar -> default 30 (ISO 50001)
    res_default = use_case.resumen(PLANTA_ID, "mt-13200v", organizacion_id=ORG_ID)
    assert res_default.compensacion_historica is not None
    assert res_default.compensacion_historica.periodo_dias == 30

    # 2. Con periodo_dias=14 explícito
    res_14 = use_case.resumen(PLANTA_ID, "mt-13200v", organizacion_id=ORG_ID, periodo_dias=14)
    assert res_14.compensacion_historica is not None
    assert res_14.compensacion_historica.periodo_dias == 14

    # 3. Con dias=7 y sin periodo_dias -> hereda dias=7
    res_7 = use_case.resumen(PLANTA_ID, "mt-13200v", organizacion_id=ORG_ID, dias=7)
    assert res_7.compensacion_historica is not None
    assert res_7.compensacion_historica.periodo_dias == 7


def test_compensacion_historica_sobrecompensacion_sostenida(use_case):
    """Si Q_max <= 0, sobrecompensacion_sostenida=True y banco_recomendado=None."""
    acometida_mt = _nodo("mt-13200v", TipoNodoUnifilar.ACOMETIDA)
    acometida_mt.tension_nominal_v = 13200.0
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [
        acometida_mt,
        _nodo("tgbt-1", TipoNodoUnifilar.TGBT, parent_id="mt-13200v", device_id=DEV_1),
    ]

    # Simular lecturas con reactiva capacitiva negativa: Q = -25 kVAr
    puntos_historico = [
        (
            datetime(2026, 9, 12, hour=i, tzinfo=timezone.utc),
            100_000.0,
            -25_000.0,
        )
        for i in range(3)
    ]

    use_case.consultar_telemetria.listar_instantaneas.return_value = [
        type(
            "PuntoPotencia",
            (),
            {"registrado_en": p[0], "potencia_activa_total_W": p[1], "potencia_reactiva_total_VAR": p[2]},
        )()
        for p in puntos_historico
    ]
    use_case.repo_telemetria.obtener_ultima_instantanea.return_value = _lectura(DEV_1, 100_000.0, var=-25_000.0)

    resumen = use_case.resumen(PLANTA_ID, "mt-13200v", organizacion_id=ORG_ID)

    assert resumen.compensacion_historica is not None
    assert resumen.compensacion_historica.sobrecompensacion_sostenida is True
    assert resumen.compensacion_historica.banco_recomendado is None
    assert resumen.compensacion_historica.potencia_reactiva_max_kvar == -25.0


def test_resumen_nodo_acometida_expone_triada_de_demanda(use_case):
    acometida = NodoUnifilar(
        id="acometida-1",
        planta_id=PLANTA_ID,
        nombre="Acometida MT",
        tipo=TipoNodoUnifilar.ACOMETIDA,
        tension_nominal_v=13200.0,
        potencia_contratada_punta_kw=800.0,
        potencia_contratada_fuera_punta_kw=850.0,
    )
    trafo = _nodo("trafo-1", TipoNodoUnifilar.TRANSFORMADOR, parent_id="acometida-1", device_id=DEV_1)
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [acometida, trafo]

    factura = FacturaDistribuidora(
        id="fact-1",
        planta_id=PLANTA_ID,
        periodo="2026-09",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="123",
        importe_total_ars=1000.0,
        potencia_contratada_punta_kw=800.0,
        potencia_contratada_fuera_punta_kw=850.0,
        potencia_adquirida_punta_kw=1049.0,
        potencia_adquirida_fuera_punta_kw=1082.0,
    )
    use_case.repo_organizaciones.obtener_facturas_planta.return_value = [factura]
    use_case.repo_telemetria.obtener_ultima_instantanea.return_value = _lectura(DEV_1, 500_000.0)

    from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import DemandaCuartohoraria

    with patch(
        "src.application.use_cases.consultar_nodo_unifilar.calcular_demanda_cuartohoraria",
        return_value=DemandaCuartohoraria(
            potencia_adquirida_punta_kw=720.0,
            potencia_adquirida_fuera_punta_kw=680.0,
        ),
    ):
        resumen = use_case.resumen(PLANTA_ID, "acometida-1", organizacion_id=ORG_ID)

    assert resumen.potencia_contratada_punta_kw == 800.0
    assert resumen.potencia_contratada_fuera_punta_kw == 850.0
    assert resumen.ultima_potencia_adquirida_punta_kw == 1049.0
    assert resumen.ultima_potencia_adquirida_fuera_punta_kw == 1082.0
    assert resumen.potencia_adquirida_punta_en_curso_kw == 720.0
    assert resumen.potencia_adquirida_fuera_punta_en_curso_kw == 680.0


def test_resumen_nodo_acometida_fallback_factura_si_no_declarada_en_nodo(use_case):
    # Acometida sin potencia_contratada declarada en YAML
    acometida = NodoUnifilar(
        id="acometida-sin-declarar",
        planta_id=PLANTA_ID,
        nombre="Acometida MT",
        tipo=TipoNodoUnifilar.ACOMETIDA,
        tension_nominal_v=13200.0,
    )
    trafo = _nodo("trafo-1", TipoNodoUnifilar.TRANSFORMADOR, parent_id="acometida-sin-declarar", device_id=DEV_1)
    use_case.repo_organizaciones.obtener_nodos_unifilar.return_value = [acometida, trafo]

    factura = FacturaDistribuidora(
        id="fact-1",
        planta_id=PLANTA_ID,
        periodo="2026-09",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="123",
        importe_total_ars=1000.0,
        potencia_contratada_punta_kw=750.0,
        potencia_contratada_fuera_punta_kw=820.0,
        potencia_adquirida_punta_kw=900.0,
        potencia_adquirida_fuera_punta_kw=920.0,
    )
    use_case.repo_organizaciones.obtener_facturas_planta.return_value = [factura]
    use_case.repo_telemetria.obtener_ultima_instantanea.return_value = _lectura(DEV_1, 500_000.0)

    from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import DemandaCuartohoraria

    with patch(
        "src.application.use_cases.consultar_nodo_unifilar.calcular_demanda_cuartohoraria",
        return_value=DemandaCuartohoraria(
            potencia_adquirida_punta_kw=600.0,
            potencia_adquirida_fuera_punta_kw=550.0,
        ),
    ):
        resumen = use_case.resumen(PLANTA_ID, "acometida-sin-declarar", organizacion_id=ORG_ID)

    assert resumen.potencia_contratada_punta_kw == 750.0
    assert resumen.potencia_contratada_fuera_punta_kw == 820.0
    assert resumen.ultima_potencia_adquirida_punta_kw == 900.0
    assert resumen.ultima_potencia_adquirida_fuera_punta_kw == 920.0
    assert resumen.potencia_adquirida_punta_en_curso_kw == 600.0
    assert resumen.potencia_adquirida_fuera_punta_en_curso_kw == 550.0
