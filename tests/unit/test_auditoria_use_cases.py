"""tests/unit/test_auditoria_use_cases.py — Tests para casos de uso de auditoría."""

from datetime import datetime

from src.application.dtos.audit_dto import (
    ConsultarAuditLogsQueryDTO,
    RegistrarAuditLogDTO,
)
from src.application.use_cases.gestionar_auditoria import (
    ConsultarAuditLogsUseCase,
    RegistrarEventoAuditoriaUseCase,
)
from src.domain.auditoria.entities import RegistroAuditoria
from src.domain.auditoria.ports import RepositorioAuditoriaPort


class MockAuditoriaRepository(RepositorioAuditoriaPort):
    def __init__(self):
        self.registros: list[RegistroAuditoria] = []

    def registrar(self, evento: RegistroAuditoria) -> RegistroAuditoria:
        self.registros.append(evento)
        return evento

    def listar(
        self,
        categoria: str | None = None,
        accion: str | None = None,
        actor_usuario_id: str | None = None,
        recurso_tipo: str | None = None,
        recurso_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[RegistroAuditoria]:
        resultado = list(self.registros)
        if categoria:
            resultado = [r for r in resultado if r.categoria == categoria]
        if accion:
            resultado = [r for r in resultado if r.accion == accion]
        return resultado[offset : offset + limite]

    def contar(
        self,
        categoria: str | None = None,
        accion: str | None = None,
        actor_usuario_id: str | None = None,
        recurso_tipo: str | None = None,
        recurso_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> int:
        return len(self.listar(categoria=categoria, accion=accion))


def test_registrar_evento_auditoria_sanitiza_secretos():
    repo = MockAuditoriaRepository()
    use_case = RegistrarEventoAuditoriaUseCase(repo)

    dto = RegistrarAuditLogDTO(
        categoria="AUTH",
        accion="LOGIN_EXITOSO",
        resultado="EXITO",
        actor_usuario_id="user-123",
        actor_email="admin@datamaq.local",
        metadatos={"password": "123", "normal": "valor"},
    )

    resultado = use_case.ejecutar(dto)
    assert resultado.id is not None
    assert resultado.categoria == "AUTH"
    assert resultado.resultado == "EXITO"
    assert resultado.metadatos is not None
    assert resultado.metadatos["password"] == "[REDACTED]"
    assert resultado.metadatos["normal"] == "valor"
    assert len(repo.registros) == 1


def test_consultar_audit_logs_use_case():
    repo = MockAuditoriaRepository()
    reg_use_case = RegistrarEventoAuditoriaUseCase(repo)
    consulta_use_case = ConsultarAuditLogsUseCase(repo)

    reg_use_case.ejecutar(
        RegistrarAuditLogDTO(
            categoria="AUTH",
            accion="LOGIN_EXITOSO",
            resultado="EXITO",
        )
    )
    reg_use_case.ejecutar(
        RegistrarAuditLogDTO(
            categoria="METROLOGIA",
            accion="CALIBRACION_ACTUALIZADA",
            resultado="EXITO",
        )
    )

    todos = consulta_use_case.ejecutar(ConsultarAuditLogsQueryDTO())
    assert len(todos) == 2

    filtrados = consulta_use_case.ejecutar(ConsultarAuditLogsQueryDTO(categoria="METROLOGIA"))
    assert len(filtrados) == 1
    assert filtrados[0].accion == "CALIBRACION_ACTUALIZADA"
