"""tests/unit/test_gestionar_activos_unifilar_use_case.py — Tests para GestionarActivosUnifilarUseCase."""

import pytest

from src.application.dtos.activo_unifilar_dto import (
    ActualizarActivoUnifilarDTO,
    CrearActivoUnifilarDTO,
)
from src.application.use_cases.gestionar_activos_unifilar import (
    GestionarActivosUnifilarUseCase,
)
from src.domain.telemetria.entities import ActivoUnifilar, NodoUnifilar
from src.domain.telemetria.exceptions import ActivoUnifilarNoEncontradoError
from src.domain.telemetria.ports import (
    RepositorioActivosUnifilarPort,
    RepositorioOrganizacionesPort,
)
from src.domain.telemetria.value_objects import TipoActivoUnifilar, TipoNodoUnifilar


class FakeActivosRepository(RepositorioActivosUnifilarPort):
    def __init__(self) -> None:
        self.activos: dict[str, ActivoUnifilar] = {}

    def guardar(self, activo: ActivoUnifilar) -> ActivoUnifilar:
        self.activos[activo.id] = activo
        return activo

    def obtener_por_id(self, activo_id: str) -> ActivoUnifilar | None:
        return self.activos.get(activo_id)

    def listar_por_planta(self, planta_id: str) -> list[ActivoUnifilar]:
        return [a for a in self.activos.values() if a.planta_id == planta_id]

    def eliminar(self, activo_id: str) -> bool:
        if activo_id in self.activos:
            del self.activos[activo_id]
            return True
        return False

    def guardar_lote(self, activos: list[ActivoUnifilar]) -> list[ActivoUnifilar]:
        for a in activos:
            self.activos[a.id] = a
        return activos


class FakeOrganizacionesRepository(RepositorioOrganizacionesPort):
    def __init__(self, nodos: list[NodoUnifilar]) -> None:
        self.nodos = nodos

    def obtener_por_id(self, organizacion_id: str):
        return None

    def listar_organizaciones(self):
        return []

    def obtener_planta_por_id(self, planta_id: str):
        return None

    def listar_plantas(self, organizacion_id: str | None = None):
        return []

    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        return [n for n in self.nodos if n.planta_id == planta_id]

    def obtener_zonas_planta(self, planta_id: str):
        return []

    def obtener_dispositivos_layout(self, planta_id: str):
        return []

    def obtener_instalacion_medidor(self, dispositivo_id: str):
        return None


def test_crear_activo_genera_id_si_no_se_provee():
    repo = FakeActivosRepository()
    use_case = GestionarActivosUnifilarUseCase(repo_activos=repo)

    dto = CrearActivoUnifilarDTO(
        planta_id="planta-1",
        nombre="Compresor 1",
        tipo="MAQUINA",
        tension_nominal_v=380.0,
        potencia_nominal_kw=45.0,
        categoria_uso="Fuerza Motriz",
        uso_significativo=True,
    )

    res = use_case.crear_activo(dto)
    assert res.id.startswith("act_")
    assert res.nombre == "Compresor 1"
    assert res.tipo == "MAQUINA"
    assert res.potencia_nominal_kw == 45.0
    assert res.uso_significativo is True
    assert repo.obtener_por_id(res.id) is not None


def test_crear_activo_con_id_especifico():
    repo = FakeActivosRepository()
    use_case = GestionarActivosUnifilarUseCase(repo_activos=repo)

    dto = CrearActivoUnifilarDTO(
        id="ts-mecanizado",
        planta_id="planta-1",
        nombre="Tablero Mecanizado",
        tipo="TABLERO_SECCIONAL",
        tension_nominal_v=380.0,
    )

    res = use_case.crear_activo(dto)
    assert res.id == "ts-mecanizado"
    assert repo.obtener_por_id("ts-mecanizado") is not None


def test_obtener_activo_existente_e_inexistente():
    repo = FakeActivosRepository()
    use_case = GestionarActivosUnifilarUseCase(repo_activos=repo)

    use_case.crear_activo(
        CrearActivoUnifilarDTO(
            id="act-1",
            planta_id="planta-1",
            nombre="TGBT",
            tipo="TGBT",
            tension_nominal_v=400.0,
        )
    )

    activo = use_case.obtener_activo("act-1")
    assert activo.id == "act-1"
    assert activo.nombre == "TGBT"

    with pytest.raises(ActivoUnifilarNoEncontradoError):
        use_case.obtener_activo("inexistente")


def test_actualizar_activo_parcialmente():
    repo = FakeActivosRepository()
    use_case = GestionarActivosUnifilarUseCase(repo_activos=repo)

    use_case.crear_activo(
        CrearActivoUnifilarDTO(
            id="act-upd",
            planta_id="planta-1",
            nombre="Nombre Original",
            tipo="LINEA",
            tension_nominal_v=380.0,
            posicion_x=10.0,
        )
    )

    actualizado = use_case.actualizar_activo(
        "act-upd",
        ActualizarActivoUnifilarDTO(
            nombre="Nombre Nuevo",
            posicion_x=25.0,
            categoria_uso="Climatización",
        ),
    )

    assert actualizado.nombre == "Nombre Nuevo"
    assert actualizado.posicion_x == 25.0
    assert actualizado.categoria_uso == "Climatización"
    assert actualizado.tension_nominal_v == 380.0  # Conserva lo no modificado


def test_eliminar_activo():
    repo = FakeActivosRepository()
    use_case = GestionarActivosUnifilarUseCase(repo_activos=repo)

    use_case.crear_activo(
        CrearActivoUnifilarDTO(
            id="para-borrar",
            planta_id="planta-1",
            nombre="Temporal",
            tipo="LINEA",
            tension_nominal_v=380.0,
        )
    )

    assert use_case.eliminar_activo("para-borrar") is True
    assert use_case.eliminar_activo("para-borrar") is False


def test_obtener_jerarquia_hibrida_unificada():
    # 1. Nodos inmutables del YAML
    nodos_yaml = [
        NodoUnifilar(
            id="acometida-01",
            planta_id="planta-1",
            nombre="Acometida MT Edesur",
            tipo=TipoNodoUnifilar.ACOMETIDA,
            tension_nominal_v=13200.0,
        ),
        NodoUnifilar(
            id="trafo-01",
            planta_id="planta-1",
            nombre="Transformador 1",
            tipo=TipoNodoUnifilar.TRANSFORMADOR,
            tension_nominal_v=400.0,
            parent_id="acometida-01",
        ),
    ]
    repo_yaml = FakeOrganizacionesRepository(nodos=nodos_yaml)

    # 2. Activos mutables de MySQL
    repo_activos = FakeActivosRepository()
    activo_mysql = ActivoUnifilar(
        id="ts-hornos",
        planta_id="planta-1",
        nombre="Tablero Hornos",
        tipo=TipoActivoUnifilar.TABLERO_SECCIONAL,
        tension_nominal_v=380.0,
        parent_id="trafo-01",
        categoria_uso="Hornos",
        uso_significativo=True,
    )
    repo_activos.guardar(activo_mysql)

    use_case = GestionarActivosUnifilarUseCase(
        repo_activos=repo_activos,
        repo_organizaciones=repo_yaml,
    )

    jerarquia = use_case.obtener_jerarquia_hibrida("planta-1")
    assert jerarquia.planta_id == "planta-1"
    assert len(jerarquia.nodos_inmutables) == 2
    assert len(jerarquia.activos_mutables) == 1
    assert len(jerarquia.nodos_unificados) == 3

    ids_unificados = [n.id for n in jerarquia.nodos_unificados]
    assert ids_unificados == ["acometida-01", "trafo-01", "ts-hornos"]

    # Validar que el activo mutable fue adaptado correctamente a NodoUnifilarDTO
    nodo_adaptado = next(n for n in jerarquia.nodos_unificados if n.id == "ts-hornos")
    assert nodo_adaptado.nombre == "Tablero Hornos"
    assert nodo_adaptado.tipo == "seccional"
    assert nodo_adaptado.categoria_uso == "Hornos"
    assert nodo_adaptado.uso_significativo is True
