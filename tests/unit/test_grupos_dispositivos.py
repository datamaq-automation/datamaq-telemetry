"""Grupos de dispositivos: suma de lecturas de varios medidores (ej. dos trafos de una planta)."""

import pytest

from src.application.use_cases.gestionar_grupos_dispositivos import GestionarGruposDispositivosUseCase
from src.domain.telemetria.entities import (
    Dispositivo,
    EnergiaAgregada,
    GrupoDispositivos,
    LecturaInstantanea,
    MedicionFase,
)
from src.domain.telemetria.exceptions import (
    DispositivoDePlantaDistintaError,
    GrupoDispositivosNoEncontradoError,
)
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioGruposDispositivosPort
from src.domain.telemetria.servicios.agregador_grupo_dispositivos import AgregadorGrupoDispositivosService
from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva


class MockDispositivosRepo(RepositorioDispositivosPort):
    def __init__(self):
        self.dispositivos: dict[str, Dispositivo] = {}

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        for d in self.dispositivos.values():
            if d.device_uid.valor == uid.valor:
                return d
        return None

    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def actualizar_heartbeat(
        self, dispositivo_id, estado, visto_por_ultima_vez, numero_serie=None, version_fw=None, version_hw=None
    ) -> None:
        pass


class MockGruposDispositivosRepo(RepositorioGruposDispositivosPort):
    def __init__(self):
        self.grupos: dict[str, GrupoDispositivos] = {}

    def crear(self, grupo: GrupoDispositivos) -> GrupoDispositivos:
        self.grupos[grupo.id] = grupo
        return grupo

    def obtener_por_id(self, grupo_id: str) -> GrupoDispositivos | None:
        return self.grupos.get(grupo_id)

    def listar_por_planta(self, planta_id: str) -> list[GrupoDispositivos]:
        return [g for g in self.grupos.values() if g.planta_id == planta_id]

    def agregar_miembro(self, grupo_id: str, dispositivo_id: str) -> None:
        grupo = self.grupos[grupo_id]
        if dispositivo_id not in grupo.dispositivos_ids:
            grupo.dispositivos_ids.append(dispositivo_id)

    def quitar_miembro(self, grupo_id: str, dispositivo_id: str) -> None:
        grupo = self.grupos[grupo_id]
        if dispositivo_id in grupo.dispositivos_ids:
            grupo.dispositivos_ids.remove(dispositivo_id)

    def eliminar(self, grupo_id: str) -> None:
        self.grupos.pop(grupo_id, None)

    def listar_dispositivos_miembro(self, grupo_id: str) -> list[Dispositivo]:
        return []


def _dispositivo(id_: str, planta_id: str) -> Dispositivo:
    sufijo = format(abs(hash(id_)) % 0xFF, "02X")
    return Dispositivo(id=id_, device_uid=MacAddress(f"AA:BB:CC:DD:EE:{sufijo}"), nombre=id_, planta_id=planta_id)


class TestGestionarGruposDispositivosUseCase:
    def test_crear_grupo_con_dispositivos_de_la_misma_planta(self):
        repo_grupos = MockGruposDispositivosRepo()
        repo_dispositivos = MockDispositivosRepo()
        repo_dispositivos.guardar(_dispositivo("trafo-01", "planta-durax"))
        repo_dispositivos.guardar(_dispositivo("trafo-02", "planta-durax"))
        use_case = GestionarGruposDispositivosUseCase(repo_grupos, repo_dispositivos)

        from src.application.dtos.grupo_dispositivos_dto import GrupoDispositivosCreateDTO

        dto = GrupoDispositivosCreateDTO(
            planta_id="planta-durax", nombre="Total Planta", dispositivos_ids=["trafo-01", "trafo-02"]
        )
        resultado = use_case.crear_grupo(dto)

        assert resultado.nombre == "Total Planta"
        assert set(resultado.dispositivos_ids) == {"trafo-01", "trafo-02"}

    def test_crear_grupo_rechaza_dispositivo_de_otra_planta(self):
        repo_grupos = MockGruposDispositivosRepo()
        repo_dispositivos = MockDispositivosRepo()
        repo_dispositivos.guardar(_dispositivo("trafo-01", "planta-durax"))
        repo_dispositivos.guardar(_dispositivo("medidor-otra", "otra-planta"))
        use_case = GestionarGruposDispositivosUseCase(repo_grupos, repo_dispositivos)

        from src.application.dtos.grupo_dispositivos_dto import GrupoDispositivosCreateDTO

        dto = GrupoDispositivosCreateDTO(
            planta_id="planta-durax", nombre="Total Planta", dispositivos_ids=["trafo-01", "medidor-otra"]
        )
        with pytest.raises(DispositivoDePlantaDistintaError):
            use_case.crear_grupo(dto)

    def test_agregar_miembro_rechaza_dispositivo_de_otra_planta(self):
        repo_grupos = MockGruposDispositivosRepo()
        repo_dispositivos = MockDispositivosRepo()
        repo_dispositivos.guardar(_dispositivo("medidor-otra", "otra-planta"))
        grupo = GrupoDispositivos(id="g1", planta_id="planta-durax", nombre="Total")
        repo_grupos.crear(grupo)
        use_case = GestionarGruposDispositivosUseCase(repo_grupos, repo_dispositivos)

        with pytest.raises(DispositivoDePlantaDistintaError):
            use_case.agregar_miembro("g1", "medidor-otra")

    def test_obtener_grupo_inexistente_falla(self):
        use_case = GestionarGruposDispositivosUseCase(MockGruposDispositivosRepo(), MockDispositivosRepo())
        with pytest.raises(GrupoDispositivosNoEncontradoError):
            use_case.obtener_grupo("no-existe")

    def test_quitar_miembro_y_eliminar_grupo(self):
        repo_grupos = MockGruposDispositivosRepo()
        repo_dispositivos = MockDispositivosRepo()
        grupo = GrupoDispositivos(id="g1", planta_id="planta-durax", nombre="Total", dispositivos_ids=["trafo-01"])
        repo_grupos.crear(grupo)
        use_case = GestionarGruposDispositivosUseCase(repo_grupos, repo_dispositivos)

        resultado = use_case.quitar_miembro("g1", "trafo-01")
        assert resultado.dispositivos_ids == []

        use_case.eliminar_grupo("g1")
        with pytest.raises(GrupoDispositivosNoEncontradoError):
            use_case.obtener_grupo("g1")

    def test_crear_grupo_rechaza_al_superar_el_cupo_por_planta(self):
        from src.application.dtos.grupo_dispositivos_dto import GrupoDispositivosCreateDTO
        from src.application.use_cases.gestionar_grupos_dispositivos import MAX_GRUPOS_POR_PLANTA
        from src.domain.telemetria.exceptions import LimiteGruposExcedidoError

        repo_grupos = MockGruposDispositivosRepo()
        repo_dispositivos = MockDispositivosRepo()
        for i in range(MAX_GRUPOS_POR_PLANTA):
            repo_grupos.crear(GrupoDispositivos(id=f"g{i}", planta_id="planta-durax", nombre=f"Grupo {i}"))
        use_case = GestionarGruposDispositivosUseCase(repo_grupos, repo_dispositivos)

        dto = GrupoDispositivosCreateDTO(planta_id="planta-durax", nombre="Uno de más")
        with pytest.raises(LimiteGruposExcedidoError):
            use_case.crear_grupo(dto)


def _lectura(dispositivo_id: str, vatios: float) -> LecturaInstantanea:
    from datetime import datetime, timezone

    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=datetime(2026, 9, 1, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios),
    )


class TestAgregadorGrupoDispositivosService:
    def test_suma_potencia_de_dispositivos_con_dato(self):
        lecturas = {"trafo-01": _lectura("trafo-01", 1000.0), "trafo-02": _lectura("trafo-02", 1500.0)}
        resultado = AgregadorGrupoDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 2500.0
        assert resultado.dispositivos_sin_dato == []

    def test_suma_tolera_desalineamiento_y_avisa_dispositivo_sin_dato(self):
        lecturas = {"trafo-01": _lectura("trafo-01", 1000.0), "trafo-02": None}
        resultado = AgregadorGrupoDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w == 1000.0
        assert resultado.dispositivos_sin_dato == ["trafo-02"]

    def test_suma_sin_ningun_dato_devuelve_none(self):
        lecturas = {"trafo-01": None, "trafo-02": None}
        resultado = AgregadorGrupoDispositivosService.sumar_ultimas_lecturas(lecturas)
        assert resultado.potencia_activa_total_w is None
        assert resultado.dispositivos_sin_dato == ["trafo-01", "trafo-02"]

    def test_suma_energia_agregada_por_periodo_entre_dispositivos(self):
        from datetime import date

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
        resultado = AgregadorGrupoDispositivosService.sumar_energia_agregada(agregados)
        por_periodo = {r.periodo: r.energia_activa_neta_kwh for r in resultado}
        assert por_periodo[date(2026, 9, 1)] is None
        assert por_periodo[date(2026, 9, 2)] == 15.0

    def test_suma_energia_con_un_dispositivo_sin_dato_en_el_periodo(self):
        from datetime import date

        agregados = {
            "trafo-01": [EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=10.0)],
            "trafo-02": [EnergiaAgregada(periodo=date(2026, 9, 2), energia_activa_neta_kwh=None)],
        }
        resultado = AgregadorGrupoDispositivosService.sumar_energia_agregada(agregados)
        assert resultado[0].energia_activa_neta_kwh == 10.0

    def test_sumar_potencia_en_el_tiempo_alinea_por_bucket_pese_a_desalineamiento(self):
        from datetime import datetime, timezone

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0), (base.replace(minute=5), 1100.0)],
            # Mismo bucket de 5 minutos que el primero, pero con timestamp corrido 40s.
            "trafo-02": [(base.replace(second=40), 500.0), (base.replace(minute=5, second=10), 600.0)],
        }

        resultado = AgregadorGrupoDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 2
        assert resultado[0].potencia_activa_total_w == 1500.0
        assert resultado[0].dispositivos_sin_dato == []
        assert resultado[1].potencia_activa_total_w == 1700.0

    def test_sumar_potencia_en_el_tiempo_marca_dispositivo_sin_dato_en_un_bucket(self):
        from datetime import datetime, timezone

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, 1000.0)],
            "trafo-02": [],
        }

        resultado = AgregadorGrupoDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w == 1000.0
        assert resultado[0].dispositivos_sin_dato == ["trafo-02"]

    def test_sumar_potencia_en_el_tiempo_sin_ningun_dato_en_bucket_es_none(self):
        from datetime import datetime, timezone

        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        lecturas = {
            "trafo-01": [(base, None)],
        }

        resultado = AgregadorGrupoDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=300)

        assert len(resultado) == 1
        assert resultado[0].potencia_activa_total_w is None
