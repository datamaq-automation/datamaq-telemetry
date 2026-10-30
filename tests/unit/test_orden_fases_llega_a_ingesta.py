"""tests/unit/test_orden_fases_llega_a_ingesta.py — `orden_fases` e `invertido` declarados en el YAML deben llegar al Dispositivo de ingesta.

Hoy `devices` no tiene columnas para `orden_fases` ni `invertido`, y `aplicar_instalacion` no los mapea. Si el YAML los
declara, la ingesta no los recibe y el parser no aplica `aplicar_configuracion_ti`. Este test describe el comportamiento
esperado y queda como xfail (strict) hasta que se corrija el camino: cuando se arregle, pytest marca XPASS y hay que quitar
el marcador.

Para ver el fallo real sin el marcador: `pytest --runxfail tests/unit/test_orden_fases_llega_a_ingesta.py`.
"""

import dataclasses

import pytest

from src.adapters.gateways.dispositivos_datos_maestros_gateway import DispositivosConDatosMaestrosGateway
from src.application.use_cases.ingesta.resolvedor_dispositivo import ResolvedorDispositivoIngesta
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress
from src.infrastructure.yaml import loaders
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

MOTIVO_XFAIL = (
    "Hoy se pierden: `devices` no tiene columnas para orden_fases/invertido y aplicar_instalacion no los mapea "
    "(src/domain/telemetria/servicios/datos_maestros_medidor.py:22-38); el resolver los toma de la fila con getattr "
    "(src/application/use_cases/ingesta/resolvedor_dispositivo.py:53-54). Ver el reporte de la rama."
)

ORG_YML = """organizaciones:
  - id: org-1
    nombre: Org de prueba
    plantas:
      - id: planta-1
        nombre: Planta de prueba
        medidores:
          - id: medidor-1
            device_uid: "EC:C9:FF:B5:7F:20"
            correccion_angular_fases: "R:0,S:15"
            orden_fases: [S, R, T]
            invertido: true
"""

DEVICE_ID = "medidor-1"
MAC = "EC:C9:FF:B5:7F:20"


class _RepoBaseFake:
    """Stand-in de MySQLDispositivosRepository: guarda solo las columnas que existen en `devices` (sin orden_fases ni invertido)."""

    def __init__(self) -> None:
        self.dispositivos: dict[str, Dispositivo] = {
            DEVICE_ID: Dispositivo(
                id=DEVICE_ID,
                device_uid=MacAddress(MAC),
                nombre="Powermeter-7F20",
                planta_id=None,
                estado=EstadoDispositivo.ONLINE,
            )
        }

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        for d in self.dispositivos.values():
            if d.device_uid.valor == uid.valor:
                return dataclasses.replace(d)
        return None

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        d = self.dispositivos.get(dispositivo_id)
        return dataclasses.replace(d) if d else None

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        copia = dataclasses.replace(dispositivo)
        self.dispositivos[dispositivo.id] = copia
        return copia

    def actualizar_heartbeat(
        self,
        dispositivo_id: str,
        estado: EstadoDispositivo,
        visto_por_ultima_vez,
        numero_serie=None,
        version_fw=None,
        version_hw=None,
    ) -> None:
        d = self.dispositivos.get(dispositivo_id)
        if d:
            d.estado = estado
            d.visto_por_ultima_vez = visto_por_ultima_vez


@pytest.fixture(autouse=True)
def _caches_limpias(tmp_path):
    loaders.limpiar_cache_yaml()
    ResolvedorDispositivoIngesta.limpiar_cache()
    (tmp_path / "organizaciones.yml").write_text(ORG_YML, encoding="utf-8")
    yield
    loaders.limpiar_cache_yaml()
    ResolvedorDispositivoIngesta.limpiar_cache()


@pytest.fixture
def repo_ingesta(tmp_path):
    """Mismo armado que el listener MQTT: gateway de datos maestros sobre el repo de la base y el YAML."""
    base = _RepoBaseFake()
    return DispositivosConDatosMaestrosGateway(base, YamlOrganizacionesRepository(data_dir=str(tmp_path)))


def test_control_gateway_mapea_correccion_angular_declarada_en_yaml(repo_ingesta):
    """Control (debe pasar): el mismo YAML y el mismo gateway sí mapean `correccion_angular_fases`.
    Demuestra que el medidor se encuentra y que el YAML se lee; la pérdida de los tests xfail es específica de orden_fases/invertido.
    """
    dispositivo = repo_ingesta.obtener_por_uid(MacAddress(MAC))

    assert dispositivo is not None
    assert dispositivo.correccion_angular_fases == "R:0,S:15"


@pytest.mark.xfail(strict=True, reason=MOTIVO_XFAIL)
def test_paso_1_gateway_de_datos_maestros_mapea_orden_fases_e_invertido(repo_ingesta):
    """Paso 1: DispositivosConDatosMaestrosGateway → DatosMaestrosMedidorService.aplicar_instalacion."""
    dispositivo = repo_ingesta.obtener_por_uid(MacAddress(MAC))

    assert dispositivo is not None
    assert dispositivo.orden_fases == ["S", "R", "T"]
    assert dispositivo.invertido is True


@pytest.mark.xfail(strict=True, reason=MOTIVO_XFAIL)
def test_paso_2_dispositivo_de_ingesta_recibe_orden_fases_e_invertido(repo_ingesta):
    """Extremo a extremo: el Dispositivo que devuelve ResolvedorDispositivoIngesta (lo que usa el parser)."""
    dispositivo = ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
        mac_raw=MAC,
        dev_info=None,
        ahora=None,
        repo_dispositivos=repo_ingesta,
        permitir_auto_registro=False,
    )

    assert dispositivo is not None
    assert dispositivo.orden_fases == ["S", "R", "T"]
    assert dispositivo.invertido is True
