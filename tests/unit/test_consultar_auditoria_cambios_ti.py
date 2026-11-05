"""tests/unit/test_consultar_auditoria_cambios_ti.py — caso de uso de auditoría de cambios de TI."""

from datetime import datetime, timezone
from typing import Any

from src.application.use_cases.consultar_auditoria_cambios_ti import ConsultarAuditoriaCambiosTIUseCase
from src.domain.telemetria.ports import RepositorioAuditoriaCambiosTIPort


class _RepositorioFalso(RepositorioAuditoriaCambiosTIPort):
    def __init__(self, registros: list[dict[str, Any]]) -> None:
        self.registros = registros
        self.filtros_recibidos: dict[str, Any] = {}
        self.organizacion_pedida_en_obtener: Any = "no se llamó"

    def listar(self, dispositivo_id, tipo_cambio, desde, hasta, organizacion_id=None):
        self.filtros_recibidos = {
            "dispositivo_id": dispositivo_id,
            "tipo_cambio": tipo_cambio,
            "desde": desde,
            "hasta": hasta,
            "organizacion_id": organizacion_id,
        }
        return list(self.registros)

    def obtener(self, cambio_id: int, organizacion_id=None):
        self.organizacion_pedida_en_obtener = organizacion_id
        return next((r for r in self.registros if r["id"] == cambio_id), None)


def _registro(id_: int) -> dict[str, Any]:
    return {
        "id": id_,
        "device_id": "c91713f1-0621-4a33-9279-c5327a317d96",
        "tipo_cambio": "correccion_angular",
        "valor_anterior": "R:180,S:-120",
        "valor_nuevo": "R:-60,S:0",
        "motivo": "banco fijo",
        "commit_git": "fdfea7d",
        "usuario": "agustin",
        "timestamp": datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc),
    }


def test_listar_pasa_los_filtros_al_repositorio():
    repo = _RepositorioFalso([_registro(1)])
    desde = datetime(2026, 10, 1, tzinfo=timezone.utc)

    resultado = ConsultarAuditoriaCambiosTIUseCase(repo).listar(
        dispositivo_id="c91713f1", tipo_cambio="correccion_angular", desde=desde, todas_las_organizaciones=True
    )

    assert [r["id"] for r in resultado] == [1]
    assert repo.filtros_recibidos == {
        "dispositivo_id": "c91713f1",
        "tipo_cambio": "correccion_angular",
        "desde": desde,
        "hasta": None,
        "organizacion_id": None,
    }


def test_listar_sin_filtros_no_filtra():
    repo = _RepositorioFalso([])
    ConsultarAuditoriaCambiosTIUseCase(repo).listar(todas_las_organizaciones=True)
    assert repo.filtros_recibidos == {
        "dispositivo_id": None,
        "tipo_cambio": None,
        "desde": None,
        "hasta": None,
        "organizacion_id": None,
    }


def test_detalle_devuelve_el_registro_existente():
    repo = _RepositorioFalso([_registro(7)])
    assert (
        ConsultarAuditoriaCambiosTIUseCase(repo).detalle(7, todas_las_organizaciones=True)["valor_nuevo"] == "R:-60,S:0"
    )


def test_detalle_devuelve_none_si_no_existe():
    repo = _RepositorioFalso([_registro(7)])
    assert ConsultarAuditoriaCambiosTIUseCase(repo).detalle(99, todas_las_organizaciones=True) is None


# --- Alcance por organización (datamaq#128) -----------------------------------------------------------------------


def test_listar_sin_organizacion_ni_alcance_total_no_consulta_el_repositorio():
    repo = _RepositorioFalso([_registro(1)])

    assert ConsultarAuditoriaCambiosTIUseCase(repo).listar() == []
    assert ConsultarAuditoriaCambiosTIUseCase(repo).listar(organizacion_id="") == []
    assert repo.filtros_recibidos == {}


def test_listar_con_organizacion_se_la_pasa_al_repositorio():
    repo = _RepositorioFalso([_registro(1)])

    ConsultarAuditoriaCambiosTIUseCase(repo).listar(organizacion_id="org-a")

    assert repo.filtros_recibidos["organizacion_id"] == "org-a"


def test_alcance_total_no_filtra_aunque_venga_una_organizacion():
    repo = _RepositorioFalso([_registro(1)])

    ConsultarAuditoriaCambiosTIUseCase(repo).listar(organizacion_id="org-a", todas_las_organizaciones=True)

    assert repo.filtros_recibidos["organizacion_id"] is None


def test_detalle_sin_organizacion_ni_alcance_total_no_consulta_el_repositorio():
    repo = _RepositorioFalso([_registro(7)])

    assert ConsultarAuditoriaCambiosTIUseCase(repo).detalle(7) is None
    assert repo.organizacion_pedida_en_obtener == "no se llamó"


def test_detalle_con_organizacion_se_la_pasa_al_repositorio():
    repo = _RepositorioFalso([_registro(7)])

    assert ConsultarAuditoriaCambiosTIUseCase(repo).detalle(7, organizacion_id="org-a") is not None
    assert repo.organizacion_pedida_en_obtener == "org-a"
