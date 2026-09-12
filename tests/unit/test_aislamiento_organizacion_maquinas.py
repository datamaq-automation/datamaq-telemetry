"""tests/unit/test_aislamiento_organizacion_maquinas.py — Aislamiento por organización al dar de alta Maquina/ParadaProgramada (hallazgo del frontend)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.dtos.disponibilidad_dto import ParadaProgramadaCreateDTO
from src.application.dtos.maquina_dto import MaquinaCreateDTO
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase
from src.domain.disponibilidad.entities import Maquina
from src.domain.disponibilidad.exceptions import DispositivoDeOrganizacionDistintaError
from src.domain.disponibilidad.ports import (
    RepositorioEventosDisponibilidadPort,
    RepositorioMaquinasPort,
    RepositorioParadasProgramadasPort,
)
from src.domain.telemetria.entities import Dispositivo, Organizacion, Planta
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import MacAddress

ORG_A = "org-a"
ORG_B = "org-b"
PLANTA_A = "planta-a"
PLANTA_B = "planta-b"


class MockDispositivosRepo(RepositorioDispositivosPort):
    def __init__(self):
        self.dispositivos: dict[str, Dispositivo] = {}

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        return None

    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def actualizar_heartbeat(self, dispositivo_id, estado, visto_por_ultima_vez, **kwargs) -> None:
        pass


class MockOrganizacionesRepo(RepositorioOrganizacionesPort):
    def __init__(self):
        self.plantas: dict[str, Planta] = {}

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        return None

    def listar_organizaciones(self) -> list[Organizacion]:
        return []

    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        return org

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        return self.plantas.get(planta_id)

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        return []

    def guardar_planta(self, planta: Planta) -> Planta:
        self.plantas[planta.id] = planta
        return planta

    def obtener_nodos_unifilar(self, planta_id: str):
        return []

    def guardar_nodos_unifilar(self, planta_id: str, nodos):
        return nodos

    def obtener_zonas_planta(self, planta_id: str):
        return []

    def obtener_dispositivos_layout(self, planta_id: str):
        return []

    def guardar_layout_planta(self, planta_id: str, plano_svg_url, zonas, dispositivos) -> None:
        pass


class MockMaquinasRepo(RepositorioMaquinasPort):
    def __init__(self):
        self.maquinas: dict[str, Maquina] = {}

    def obtener_por_id(self, maquina_id: str) -> Maquina | None:
        return self.maquinas.get(maquina_id)

    def obtener_por_dispositivo_id(self, dispositivo_id: str) -> Maquina | None:
        return next((m for m in self.maquinas.values() if m.dispositivo_id == dispositivo_id), None)

    def listar(self, organizacion_id: str | None = None) -> list[Maquina]:
        return list(self.maquinas.values())

    def guardar(self, maquina: Maquina) -> Maquina:
        self.maquinas[maquina.id] = maquina
        return maquina


class MockEventosRepo(RepositorioEventosDisponibilidadPort):
    def obtener_por_id(self, evento_id: int):
        return None

    def obtener_evento_abierto(self, maquina_id: str):
        return None

    def listar_por_maquina(self, maquina_id: str, limite: int = 100):
        return []

    def listar_por_rango(self, maquina_id: str, desde, hasta):
        return []

    def guardar(self, evento):
        return evento


class MockParadasRepo(RepositorioParadasProgramadasPort):
    def __init__(self):
        self.paradas = []

    def listar_por_maquina(self, maquina_id: str):
        return [p for p in self.paradas if p.maquina_id == maquina_id]

    def buscar_vigente(self, maquina_id: str, instante):
        return None

    def guardar(self, parada):
        self.paradas.append(parada)
        return parada


def _armar_repos_con_dispositivo(planta_id: str, organizacion_id: str, dispositivo_id: str = "dev-1"):
    repo_disp = MockDispositivosRepo()
    repo_org = MockOrganizacionesRepo()
    repo_org.guardar_planta(Planta(id=planta_id, organizacion_id=organizacion_id, nombre="Planta"))
    repo_disp.guardar(
        Dispositivo(id=dispositivo_id, device_uid=MacAddress("AABBCCDDEE01"), nombre="Medidor", planta_id=planta_id)
    )
    return repo_disp, repo_org


class TestRegistrarMaquinaAislamiento:
    def test_acepta_dispositivo_de_la_misma_organizacion(self):
        repo_disp, repo_org = _armar_repos_con_dispositivo(PLANTA_A, ORG_A)
        repo_maq = MockMaquinasRepo()
        uc = GestionarMaquinasUseCase(
            repo_maq, repo_telemetria=None, repo_dispositivos=repo_disp, repo_organizaciones=repo_org
        )

        dto = MaquinaCreateDTO(dispositivo_id="dev-1", nombre="Torno")
        resultado = uc.registrar_maquina(dto, organizacion_id=ORG_A)

        assert resultado.dispositivo_id == "dev-1"

    def test_rechaza_dispositivo_de_otra_organizacion(self):
        repo_disp, repo_org = _armar_repos_con_dispositivo(PLANTA_A, ORG_A)
        repo_maq = MockMaquinasRepo()
        uc = GestionarMaquinasUseCase(
            repo_maq, repo_telemetria=None, repo_dispositivos=repo_disp, repo_organizaciones=repo_org
        )

        dto = MaquinaCreateDTO(dispositivo_id="dev-1", nombre="Torno")
        with pytest.raises(DispositivoDeOrganizacionDistintaError):
            uc.registrar_maquina(dto, organizacion_id=ORG_B)

    def test_rechaza_dispositivo_inexistente(self):
        repo_disp = MockDispositivosRepo()
        repo_org = MockOrganizacionesRepo()
        repo_maq = MockMaquinasRepo()
        uc = GestionarMaquinasUseCase(
            repo_maq, repo_telemetria=None, repo_dispositivos=repo_disp, repo_organizaciones=repo_org
        )

        dto = MaquinaCreateDTO(dispositivo_id="no-existe", nombre="Torno")
        with pytest.raises(DispositivoNoEncontradoError):
            uc.registrar_maquina(dto, organizacion_id=ORG_A)

    def test_organizacion_none_no_valida_ownership(self):
        """Comportamiento preservado: superadmin, y call sites que no pasan el parámetro
        (ej. mqtt_listener.py), siguen sin validación de propiedad."""
        repo_maq = MockMaquinasRepo()
        uc = GestionarMaquinasUseCase(repo_maq, repo_telemetria=None)

        dto = MaquinaCreateDTO(dispositivo_id="dev-cualquiera", nombre="Torno")
        resultado = uc.registrar_maquina(dto)

        assert resultado.dispositivo_id == "dev-cualquiera"


class TestRegistrarParadaProgramadaAislamiento:
    def test_rechaza_maquina_de_otra_organizacion(self):
        repo_disp, repo_org = _armar_repos_con_dispositivo(PLANTA_A, ORG_A)
        repo_maq = MockMaquinasRepo()
        repo_maq.guardar(Maquina(id="m1", dispositivo_id="dev-1", nombre="Torno"))
        uc = GestionarDisponibilidadUseCase(
            repo_maq, MockEventosRepo(), MockParadasRepo(), repo_dispositivos=repo_disp, repo_organizaciones=repo_org
        )

        ahora = datetime.now(timezone.utc)
        dto = ParadaProgramadaCreateDTO(
            maquina_id="m1", inicio_at=ahora, fin_at=ahora + timedelta(hours=1), motivo="Mantenimiento"
        )
        with pytest.raises(DispositivoDeOrganizacionDistintaError):
            uc.registrar_parada_programada(dto, usuario_id="u1", organizacion_id=ORG_B)

    def test_acepta_maquina_de_la_misma_organizacion(self):
        repo_disp, repo_org = _armar_repos_con_dispositivo(PLANTA_A, ORG_A)
        repo_maq = MockMaquinasRepo()
        repo_maq.guardar(Maquina(id="m1", dispositivo_id="dev-1", nombre="Torno"))
        uc = GestionarDisponibilidadUseCase(
            repo_maq, MockEventosRepo(), MockParadasRepo(), repo_dispositivos=repo_disp, repo_organizaciones=repo_org
        )

        ahora = datetime.now(timezone.utc)
        dto = ParadaProgramadaCreateDTO(
            maquina_id="m1", inicio_at=ahora, fin_at=ahora + timedelta(hours=1), motivo="Mantenimiento"
        )
        resultado = uc.registrar_parada_programada(dto, usuario_id="u1", organizacion_id=ORG_A)

        assert resultado.maquina_id == "m1"
