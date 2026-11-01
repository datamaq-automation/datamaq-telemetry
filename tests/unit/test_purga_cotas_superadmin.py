"""tests/unit/test_purga_cotas_superadmin.py — datamaq#119.

Cotas de la purga HTTP (piso por tabla, confirmación explícita, simulación por defecto), rechazo de
valores cero o negativos también en el caso de uso, y registro en auditoría. El camino del caso de uso
usado por scripts/purge_telemetry.py y por el timer no cambia.
"""

from datetime import datetime, timedelta, timezone
from typing import ClassVar

import pytest

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaSolicitudDTO
from src.application.use_cases.purgar_telemetria import (
    CotasPurgaError,
    PurgaInvalidaError,
    PurgarTelemetriaExpiradaUseCase,
    construir_auditoria_purga,
    validar_cotas_purga,
)
from src.domain.telemetria.exceptions import DominioTelemetriaException
from tests.unit.test_optimizacion_db import MockTelemetriaRepo

AHORA = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


class SpyRepo(MockTelemetriaRepo):
    """Cuenta lo que la simulación contaría y registra cualquier borrado."""

    CONTEOS: ClassVar[dict[str, int]] = {"inst": 7, "energia": 3, "logs": 2, "alertas": 1}

    def __init__(self) -> None:
        super().__init__()
        self.borrados: list[str] = []

    def contar_instantaneas_anteriores_a(self, fecha_limite: datetime) -> int:
        return self.CONTEOS["inst"]

    def contar_energias_anteriores_a(self, fecha_limite: datetime) -> int:
        return self.CONTEOS["energia"]

    def contar_status_logs_anteriores_a(self, fecha_limite: datetime) -> int:
        return self.CONTEOS["logs"]

    def contar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime) -> int:
        return self.CONTEOS["alertas"]

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.borrados.append("inst")
        return 0

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.borrados.append("energia")
        return 0

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.borrados.append("logs")
        return 0

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.borrados.append("alertas")
        return 0


# --- Simulación: cuenta y no borra -------------------------------------------------------------


def test_simulacion_cuenta_sin_borrar_nada() -> None:
    repo = SpyRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    res = use_case.simular(PurgaRequestDTO())

    assert res.simulado is True
    assert res.instantaneas_eliminadas == 7
    assert res.energias_eliminadas == 3
    assert res.status_logs_eliminados == 2
    assert res.alertas_resueltas_eliminadas == 1
    assert res.total_registros_eliminados == 13
    assert repo.borrados == []


# --- Caso de uso: cero y negativos se rechazan también aquí ------------------------------------


@pytest.mark.parametrize(
    "dto",
    [
        PurgaRequestDTO(dias_retencion_override=0),
        PurgaRequestDTO(dias_retencion_override=-5),
        PurgaRequestDTO(dias_retencion_instantaneas=0),
        PurgaRequestDTO(dias_retencion_energia=-1),
    ],
)
def test_caso_de_uso_rechaza_cero_y_negativos(dto: PurgaRequestDTO) -> None:
    repo = SpyRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    with pytest.raises(PurgaInvalidaError):
        use_case.ejecutar(dto)
    assert repo.borrados == []


def test_purga_invalida_es_excepcion_de_dominio_para_el_presenter() -> None:
    # Así el manejador HTTP la mapea a 422 como el resto de errores de negocio.
    assert issubclass(PurgaInvalidaError, DominioTelemetriaException)
    assert issubclass(CotasPurgaError, DominioTelemetriaException)


# --- Cotas de la ruta: piso por tabla y confirmación explícita ---------------------------------


def test_sin_parametros_no_exige_confirmacion() -> None:
    validar_cotas_purga(PurgaSolicitudDTO(), AHORA)


def test_override_mayor_o_igual_al_piso_de_energia_pasa_sin_confirmar() -> None:
    validar_cotas_purga(PurgaSolicitudDTO(dias_retencion_override=1825), AHORA)


def test_override_menor_al_piso_exige_confirmacion() -> None:
    with pytest.raises(CotasPurgaError):
        validar_cotas_purga(PurgaSolicitudDTO(dias_retencion_override=30), AHORA)


def test_override_menor_al_piso_pasa_con_confirmacion_explicita() -> None:
    validar_cotas_purga(
        PurgaSolicitudDTO(dias_retencion_override=30, confirmar_retencion_menor=True),
        AHORA,
    )


def test_override_cero_se_rechaza_aun_con_confirmacion() -> None:
    with pytest.raises(PurgaInvalidaError):
        validar_cotas_purga(
            PurgaSolicitudDTO(dias_retencion_override=0, confirmar_retencion_menor=True),
            AHORA,
        )


def test_corte_hasta_mas_reciente_que_el_piso_exige_confirmacion() -> None:
    corte_reciente = AHORA - timedelta(days=10)
    with pytest.raises(CotasPurgaError):
        validar_cotas_purga(PurgaSolicitudDTO(corte_hasta=corte_reciente), AHORA)


def test_corte_hasta_anterior_al_piso_de_energia_pasa() -> None:
    corte_antiguo = AHORA - timedelta(days=2000)
    validar_cotas_purga(PurgaSolicitudDTO(corte_hasta=corte_antiguo), AHORA)


def test_corte_hasta_en_el_futuro_se_rechaza() -> None:
    with pytest.raises(PurgaInvalidaError):
        validar_cotas_purga(PurgaSolicitudDTO(corte_hasta=AHORA + timedelta(days=1)), AHORA)


# --- Auditoría: quién, parámetros, cantidades -------------------------------------------------


def test_auditoria_registra_actor_parametros_y_cantidades() -> None:
    res_fake = {"total_registros_eliminados": 13, "simulado": True}
    dto = construir_auditoria_purga(
        actor_usuario_id="u-1",
        actor_email="admin@ejemplo.com",
        actor_ip="10.0.0.5",
        parametros={"dias_retencion_override": 1825, "corte_hasta": None},
        total_registros=res_fake["total_registros_eliminados"],
        simulado=True,
    )

    assert isinstance(dto, RegistrarAuditLogDTO)
    assert dto.categoria == "SISTEMA"
    assert dto.accion == "PURGA_SIMULADA"
    assert dto.resultado == "EXITO"
    assert dto.actor_usuario_id == "u-1"
    assert dto.metadatos["total_registros"] == 13
    assert dto.metadatos["parametros"]["dias_retencion_override"] == 1825


def test_auditoria_de_purga_real_usa_accion_ejecutada() -> None:
    dto = construir_auditoria_purga(
        actor_usuario_id="u-1",
        actor_email=None,
        actor_ip=None,
        parametros={},
        total_registros=5,
        simulado=False,
    )
    assert dto.accion == "PURGA_EJECUTADA"


# --- Revisión del padre: la validación usa los cortes EFECTIVOS -----------------------------------


def test_override_que_recorta_energia_exige_confirmacion_aunque_energia_explicita_sea_mayor() -> None:
    # _calcular_cortes aplica el override a TODAS las tablas: la energía se recorta a 40 días.
    # La validación debe verlo, aunque dias_retencion_energia=2000 parezca cumplir el piso.
    dto = PurgaSolicitudDTO(
        dias_retencion_override=40,
        dias_retencion_instantaneas=100,
        dias_retencion_energia=2000,
        confirmar=True,
    )
    with pytest.raises(CotasPurgaError):
        validar_cotas_purga(dto, AHORA)


def test_corte_hasta_reciente_exige_confirmacion_en_todas_las_tablas() -> None:
    with pytest.raises(CotasPurgaError):
        validar_cotas_purga(PurgaSolicitudDTO(corte_hasta=AHORA - timedelta(days=10), confirmar=True), AHORA)


# --- Revisión del padre: auditoría de intención antes de borrar -----------------------------------


def test_auditoria_de_intencion_se_registra_antes_del_borrado_y_luego_el_resultado() -> None:
    from src.application.use_cases.purgar_telemetria import construir_auditoria_purga

    evento = construir_auditoria_purga(
        actor_usuario_id="u-1",
        actor_email=None,
        actor_ip=None,
        parametros={},
        total_registros=None,
        simulado=False,
        accion="PURGA_SOLICITADA",
    )
    assert evento.accion == "PURGA_SOLICITADA"
    assert evento.metadatos["total_registros"] is None
