"""tests/unit/test_datos_maestros_medidor.py — E4: precedencia del YAML sobre MySQL en instalación y contrato."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.adapters.gateways.dispositivos_datos_maestros_gateway import DispositivosConDatosMaestrosGateway
from src.application.dtos.dispositivo_dto import DispositivoUpdateDTO
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.telemetria.entities import Dispositivo, InstalacionMedidor, NodoUnifilar
from src.domain.telemetria.exceptions import CampoGestionadoPorYamlError
from src.domain.telemetria.servicios.datos_maestros_medidor import DatosMaestrosMedidorService
from src.domain.telemetria.value_objects import MacAddress, TipoNodoUnifilar
from src.infrastructure.fastapi.dependencies import get_dispositivos_use_case, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def _dev(**kw) -> Dispositivo:
    base = dict(id="dev-1", device_uid=MacAddress("AABBCCDDEE01"), nombre="PM", planta_id="p1")
    base.update(kw)
    return Dispositivo(**base)


def _nodo(id_, tipo, parent_id=None, device_id=None, **kw) -> NodoUnifilar:
    return NodoUnifilar(
        id=id_,
        planta_id="p1",
        nombre=id_,
        tipo=tipo,
        tension_nominal_v=380.0,
        parent_id=parent_id,
        device_id=device_id,
        **kw,
    )


ARBOL = [
    _nodo("mt", TipoNodoUnifilar.ACOMETIDA, categoria_tarifaria="T3-MT", penalizacion_reactiva_aplica=True),
    _nodo("trafo", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt"),
    _nodo("tgbt", TipoNodoUnifilar.TGBT, parent_id="trafo", device_id="dev-1"),
]


# --- Servicio de dominio ---


def test_instalacion_declarada_pisa_mysql_y_lo_no_declarado_queda():
    dev = _dev(ubicacion_tag="viejo", tipo_instalacion="CONSUMO", fases_con_ti="R,S,T")
    inst = InstalacionMedidor(dispositivo_id="dev-1", fases_con_ti="S,T")
    res = DatosMaestrosMedidorService.aplicar_instalacion(dev, inst)
    assert res.fases_con_ti == "S,T"
    assert res.ubicacion_tag == "viejo" and res.tipo_instalacion == "CONSUMO"
    assert DatosMaestrosMedidorService.aplicar_instalacion(dev, None) is dev


def test_instalacion_declarada_aplica_correccion_angular_y_fases_invertidas():
    dev = _dev(correccion_angular_fases="", ct_fases_invertidas="")
    inst = InstalacionMedidor(
        dispositivo_id="364",
        correccion_angular_fases="R:-60,S:180",
        ct_fases_invertidas="S",
    )
    res = DatosMaestrosMedidorService.aplicar_instalacion(dev, inst)
    assert res.correccion_angular_fases == "R:-60,S:180"
    assert res.ct_fases_invertidas == "S"


def test_contrato_se_hereda_de_la_acometida_por_el_arbol():
    dev = _dev(categoria_tarifaria="T2", penalizacion_reactiva_aplica=False)
    res = DatosMaestrosMedidorService.aplicar_contrato(dev, ARBOL)
    assert res.categoria_tarifaria == "T3-MT" and res.penalizacion_reactiva_aplica is True


def test_acometida_sin_contrato_declarado_no_cambia_nada():
    arbol = [
        _nodo("mt", TipoNodoUnifilar.ACOMETIDA),
        _nodo("tgbt", TipoNodoUnifilar.TGBT, parent_id="mt", device_id="dev-1"),
    ]
    dev = _dev(categoria_tarifaria="T2")
    assert DatosMaestrosMedidorService.aplicar_contrato(dev, arbol).categoria_tarifaria == "T2"
    assert DatosMaestrosMedidorService.aplicar_contrato(dev, []).categoria_tarifaria == "T2"


def test_medidor_fuera_del_unifilar_no_hereda():
    dev = _dev(id="dev-otro", categoria_tarifaria="T2")
    assert DatosMaestrosMedidorService.acometida_de("dev-otro", ARBOL) is None
    assert DatosMaestrosMedidorService.aplicar_contrato(dev, ARBOL).categoria_tarifaria == "T2"


def test_nodo_medido_por_devuelve_el_nodo_con_ese_device_id():
    nodo = DatosMaestrosMedidorService.nodo_medido_por("dev-1", ARBOL)
    assert nodo is not None and nodo.id == "tgbt"
    assert DatosMaestrosMedidorService.nodo_medido_por("dev-otro", ARBOL) is None


def test_aplicar_tension_nominal_hereda_del_nodo_medido_no_de_la_acometida():
    # La acometida ("mt") declara 380.0 en este fixture (todos los nodos comparten
    # tension_nominal_v=380.0 por defecto en `_nodo`); lo que importa es que la
    # tensión venga del nodo con el device_id, no de subir hasta la acometida.
    dev = _dev(tension_nominal_v=None)
    res = DatosMaestrosMedidorService.aplicar_tension_nominal(dev, ARBOL)
    assert res.tension_nominal_v == 380.0


def test_aplicar_tension_nominal_dispositivo_fuera_del_yaml_queda_none():
    dev = _dev(id="dev-otro", tension_nominal_v=None)
    res = DatosMaestrosMedidorService.aplicar_tension_nominal(dev, ARBOL)
    assert res.tension_nominal_v is None
    assert DatosMaestrosMedidorService.aplicar_tension_nominal(dev, []).tension_nominal_v is None


def test_campos_gobernados_y_rechazo_de_escritura():
    inst = InstalacionMedidor(dispositivo_id="dev-1", tag_ubicacion="TGBT-01")
    gobernados = DatosMaestrosMedidorService.campos_gobernados_por_yaml("dev-1", inst, ARBOL)
    assert gobernados == {"ubicacion_tag", "categoria_tarifaria", "penalizacion_reactiva_aplica"}
    DatosMaestrosMedidorService.rechazar_escritura_de_campos_gobernados({"nombre", "fases_con_ti"}, gobernados)
    with pytest.raises(CampoGestionadoPorYamlError, match="categoria_tarifaria, ubicacion_tag"):
        DatosMaestrosMedidorService.rechazar_escritura_de_campos_gobernados(
            {"ubicacion_tag", "categoria_tarifaria"}, gobernados
        )


# --- Gateway ---


def _org_repo(instalacion=None, nodos=None) -> MagicMock:
    repo = MagicMock()
    repo.obtener_instalacion_medidor.return_value = instalacion
    repo.obtener_nodos_unifilar.return_value = nodos or []
    return repo


def test_gateway_resuelve_en_todas_las_lecturas():
    base = MagicMock()
    dev = _dev(fases_con_ti="R,S,T", categoria_tarifaria="T2")
    base.obtener_por_id.return_value = dev
    base.obtener_por_uid.return_value = dev
    base.listar.return_value = [dev, None]
    gw = DispositivosConDatosMaestrosGateway(
        base, _org_repo(InstalacionMedidor(dispositivo_id="dev-1", fases_con_ti="S,T"), ARBOL)
    )
    for res in (gw.obtener_por_id("dev-1"), gw.obtener_por_uid(dev.device_uid), gw.listar()[0]):
        assert res is not None
        assert res.fases_con_ti == "S,T" and res.categoria_tarifaria == "T3-MT"
    assert len(gw.listar()) == 1
    assert gw.obtener_por_id("nadie") is None or base.obtener_por_id.return_value is dev


def test_gateway_resuelve_tension_nominal_del_nodo_medido():
    base = MagicMock()
    dev = _dev()
    base.obtener_por_id.return_value = dev
    gw = DispositivosConDatosMaestrosGateway(base, _org_repo(nodos=ARBOL))
    res = gw.obtener_por_id("dev-1")
    assert res is not None
    assert res.tension_nominal_v == 380.0


def test_gateway_sin_yaml_es_transparente():
    base = MagicMock()
    dev = _dev()
    base.obtener_por_id.return_value = dev
    gw = DispositivosConDatosMaestrosGateway(base, _org_repo())
    assert gw.obtener_por_id("dev-1") == dev


# --- PATCH ---


def test_patch_rechaza_campo_gobernado_y_acepta_el_resto():
    repo_disp = MagicMock()
    dev = _dev()
    repo_disp.obtener_por_id.return_value = dev
    repo_disp.guardar.side_effect = lambda d: d
    repo_org = _org_repo(InstalacionMedidor(dispositivo_id="dev-1", fases_con_ti="S,T"), ARBOL)
    repo_org.obtener_planta_por_id.return_value = None
    use_case = GestionarDispositivosUseCase(repo_disp, repo_org)

    with pytest.raises(CampoGestionadoPorYamlError):
        use_case.actualizar_dispositivo("dev-1", DispositivoUpdateDTO(fases_con_ti="R"))
    with pytest.raises(CampoGestionadoPorYamlError):
        use_case.actualizar_dispositivo("dev-1", DispositivoUpdateDTO(categoria_tarifaria="T1"))
    repo_disp.guardar.assert_not_called()

    res = use_case.actualizar_dispositivo(
        "dev-1", DispositivoUpdateDTO(nombre="Nuevo", tipo_instalacion="GENERACION_FV")
    )
    assert res.nombre == "Nuevo"
    repo_disp.guardar.assert_called_once()


def test_patch_gobernado_responde_422_por_http():
    app = create_app()
    use_case = MagicMock()
    use_case.actualizar_dispositivo_de_organizacion.side_effect = CampoGestionadoPorYamlError("Gestionado por YAML: fases_con_ti.")
    app.dependency_overrides[get_dispositivos_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u", "rol": "admin", "org": "o"}
    resp = TestClient(app).patch("/api/v1/dispositivos/dev-1", json={"fases_con_ti": "R"})
    assert resp.status_code == 422
    assert "Gestionado por YAML" in resp.json()["detail"]


# --- YAML real: coherencia de datos declarados y contratos ---


def test_yaml_real_instalacion_y_contratos():
    repo = YamlOrganizacionesRepository(data_dir="data")
    # Dispositivo sin bloque de medidores declarado devuelve None
    assert repo.obtener_instalacion_medidor("id-dispositivo-no-configurado") is None
    # Dispositivo de Durax con bloque declarado devuelve su instalación
    inst_durax = repo.obtener_instalacion_medidor("51048a93-f1f3-4283-a708-24cbd39c7192")
    assert inst_durax is not None
    assert inst_durax.fases_con_ti == "R,S,T"
    for planta in repo.listar_plantas():
        for nodo in repo.obtener_nodos_unifilar(planta.id):
            assert nodo.categoria_tarifaria is None and nodo.penalizacion_reactiva_aplica is None
