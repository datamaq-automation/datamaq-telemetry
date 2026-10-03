"""tests/unit/test_asistente_consentimiento.py — Tests de consentimiento Groq."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.application.dtos.asistente_dto import PreguntaRequestDTO, PreguntaResponseDTO
from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.domain.asistente.entities import RespuestaAsistente
from src.infrastructure.sqlalchemy.repositories.asistente_repository import (
    MySQLAsistenteConsentimientoRepository,
)


class TestPreguntaRequestDTO:
    """Suite: Validación de PreguntaRequestDTO con consentimiento."""

    def test_dto_sin_consentimiento_default_false(self):
        """usuario_consiente_envio_groq=False por defecto."""
        dto = PreguntaRequestDTO(pregunta="¿Cuál es el factor de potencia?")
        assert dto.usuario_consiente_envio_groq is False

    def test_dto_con_consentimiento_true(self):
        """Puede enviar usuario_consiente_envio_groq=True."""
        dto = PreguntaRequestDTO(
            pregunta="¿Cuál es el factor de potencia?",
            usuario_consiente_envio_groq=True,
        )
        assert dto.usuario_consiente_envio_groq is True

    def test_dto_validacion_pregunta_min_length(self):
        """Pregunta debe tener mínimo 2 caracteres."""
        with pytest.raises(ValueError):
            PreguntaRequestDTO(pregunta="A")

    def test_dto_conversacion_id_opcional(self):
        """conversacion_id es opcional."""
        dto = PreguntaRequestDTO(pregunta="¿Estado?")
        assert dto.conversacion_id is None

        dto2 = PreguntaRequestDTO(pregunta="¿Estado?", conversacion_id="conv-123")
        assert dto2.conversacion_id == "conv-123"


class TestPreguntaResponseDTO:
    """Suite: Validación de PreguntaResponseDTO con auditoría."""

    def test_response_con_campos_auditoria(self):
        """Response contiene campos de auditoría."""
        response = PreguntaResponseDTO(
            respuesta="Respuesta de prueba",
            intencion_detectada="EXPLICAR_ALERTAS",
            consentimiento_requerido=True,
            enviado_a_groq=False,
            razon_sin_groq="sin_consentimiento",
        )
        assert response.respuesta == "Respuesta de prueba"
        assert response.intencion_detectada == "EXPLICAR_ALERTAS"
        assert response.consentimiento_requerido is True
        assert response.enviado_a_groq is False
        assert response.razon_sin_groq == "sin_consentimiento"

    def test_response_defaults_auditoria(self):
        """Campos de auditoría tienen valores por defecto False/None."""
        response = PreguntaResponseDTO(respuesta="Respuesta")
        assert response.consentimiento_requerido is False
        assert response.enviado_a_groq is False
        assert response.razon_sin_groq is None


class TestRespuestaAsistenteEntity:
    """Suite: Entity RespuestaAsistente con campos de auditoría."""

    def test_entity_sin_consentimiento(self):
        """Entity puede estar sin consentimiento (respuesta local)."""
        respuesta = RespuestaAsistente(
            texto="Respuesta local",
            intencion="EXPLICAR_ALERTAS",
            consentimiento_requerido=True,
            enviado_a_groq=False,
            razon_sin_groq="sin_consentimiento",
        )
        assert respuesta.texto == "Respuesta local"
        assert respuesta.consentimiento_requerido is True
        assert respuesta.enviado_a_groq is False

    def test_entity_con_groq(self):
        """Entity con respuesta de Groq."""
        respuesta = RespuestaAsistente(
            texto="Respuesta de Groq",
            intencion="SALUD_DISPOSITIVOS",
            consentimiento_requerido=False,
            enviado_a_groq=True,
            razon_sin_groq=None,
        )
        assert respuesta.enviado_a_groq is True
        assert respuesta.razon_sin_groq is None

    def test_entity_frozen(self):
        """Entity es frozen (inmutable)."""
        respuesta = RespuestaAsistente(texto="Test", intencion=None)
        with pytest.raises((AttributeError, AttributeError)):
            object.__setattr__(respuesta, "texto", "Modificado")


class TestProcesarPreguntaUseCaseSinConsentimiento:
    """Suite: Use case sin consentimiento (respuesta local)."""

    @patch("src.application.use_cases.asistente.procesar_pregunta_asistente.uuid")
    def test_sin_consentimiento_retorna_respuesta_local(self, mock_uuid):
        """Sin consentimiento: respuesta local sin Groq."""
        mock_uuid.uuid4.return_value = "mock-id"

        clasificador = MagicMock()
        clasificador.clasificar.return_value = MagicMock(nombre="EXPLICAR_ALERTAS", confianza=0.95)

        generador = MagicMock()  # No debería llamarse

        repo_conv = MagicMock()
        repo_conv.crear_conversacion.return_value = MagicMock(id="conv-123")
        repo_conv.obtener_conversacion.return_value = MagicMock(id="conv-123")

        gestor_alertas = MagicMock()
        gestor_alertas.listar_alertas.return_value = []

        gestor_dispositivos = MagicMock()
        gestor_dispositivos.listar_dispositivos.return_value = []

        use_case = ProcesarPreguntaUseCaseWithDependencies(
            clasificador=clasificador,
            generador=generador,
            repo_conversaciones=repo_conv,
            gestor_alertas=gestor_alertas,
            gestor_dispositivos=gestor_dispositivos,
        )

        resultado = use_case.ejecutar(
            pregunta="¿Factor de potencia?",
            organizacion_id="org-123",
            usuario_id="user-123",
            usuario_consiente_envio_groq=False,
        )

        assert resultado.enviado_a_groq is False
        assert resultado.consentimiento_requerido is True
        assert resultado.razon_sin_groq == "sin_consentimiento"
        assert "sin IA remota" in resultado.texto or "Nota:" in resultado.texto
        generador.generar.assert_not_called()

    @patch("src.application.use_cases.asistente.procesar_pregunta_asistente.uuid")
    def test_sin_consentimiento_incluye_contexto(self, mock_uuid):
        """Sin consentimiento: respuesta local incluye datos del contexto."""
        mock_uuid.uuid4.return_value = "mock-id"

        clasificador = MagicMock()
        clasificador.clasificar.return_value = MagicMock(nombre="SALUD_DISPOSITIVOS", confianza=0.9)

        generador = MagicMock()

        repo_conv = MagicMock()
        repo_conv.crear_conversacion.return_value = MagicMock(id="conv-123")

        gestor_alertas = MagicMock()
        mock_alert_1 = MagicMock()
        mock_alert_1.model_dump.return_value = {"id": "alert-1"}
        mock_alert_2 = MagicMock()
        mock_alert_2.model_dump.return_value = {"id": "alert-2"}
        gestor_alertas.listar_alertas.return_value = [mock_alert_1, mock_alert_2]

        gestor_dispositivos = MagicMock()
        mock_dev = MagicMock()
        mock_dev.model_dump.return_value = {"id": "dev-1"}
        gestor_dispositivos.listar_dispositivos.return_value = [mock_dev]

        use_case = ProcesarPreguntaUseCaseWithDependencies(
            clasificador=clasificador,
            generador=generador,
            repo_conversaciones=repo_conv,
            gestor_alertas=gestor_alertas,
            gestor_dispositivos=gestor_dispositivos,
        )

        resultado = use_case.ejecutar(
            pregunta="¿Estado dispositivos?",
            organizacion_id="org-123",
            usuario_id="user-123",
            usuario_consiente_envio_groq=False,
        )

        # Respuesta local menciona cantidad de alertas y dispositivos
        assert "2" in resultado.texto  # 2 alertas
        assert "1" in resultado.texto  # 1 dispositivo


class TestProcesarPreguntaUseCaseConConsentimiento:
    """Suite: Use case con consentimiento (Groq)."""

    @patch("src.application.use_cases.asistente.procesar_pregunta_asistente.uuid")
    def test_con_consentimiento_llama_groq(self, mock_uuid):
        """Con consentimiento: llama a Groq."""
        mock_uuid.uuid4.return_value = "mock-id"

        clasificador = MagicMock()
        clasificador.clasificar.return_value = MagicMock(nombre="EXPLICAR_ALERTAS", confianza=0.95)

        generador = MagicMock()
        generador.generar.return_value = iter(["Respuesta ", "de ", "Groq"])

        repo_conv = MagicMock()
        repo_conv.crear_conversacion.return_value = MagicMock(id="conv-123")

        gestor_alertas = MagicMock()
        gestor_alertas.listar_alertas.return_value = []

        gestor_dispositivos = MagicMock()
        gestor_dispositivos.listar_dispositivos.return_value = []

        use_case = ProcesarPreguntaUseCaseWithDependencies(
            clasificador=clasificador,
            generador=generador,
            repo_conversaciones=repo_conv,
            gestor_alertas=gestor_alertas,
            gestor_dispositivos=gestor_dispositivos,
        )

        resultado = use_case.ejecutar(
            pregunta="¿Factor de potencia?",
            organizacion_id="org-123",
            usuario_id="user-123",
            usuario_consiente_envio_groq=True,
        )

        assert resultado.enviado_a_groq is True
        assert resultado.consentimiento_requerido is False
        assert resultado.razon_sin_groq is None
        assert resultado.texto == "Respuesta de Groq"
        generador.generar.assert_called_once()


class TestMySQLAsistenteConsentimientoRepository:
    """Suite: Repository para auditoría de consentimiento."""

    def test_guardar_consentimiento_retorna_id(self, db: Session):
        """Guardar consentimiento retorna su ID."""
        repo = MySQLAsistenteConsentimientoRepository(db)

        consentimiento_id = repo.guardar_consentimiento(
            usuario_id="user-123",
            organizacion_id="org-123",
            consentimiento_otorgado=True,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert consentimiento_id is not None
        assert isinstance(consentimiento_id, str)
        assert len(consentimiento_id) > 0

    def test_obtener_consentimiento_mas_reciente_true(self, db: Session):
        """Obtener consentimiento más reciente: True."""
        repo = MySQLAsistenteConsentimientoRepository(db)
        usuario_id = f"user-{uuid.uuid4()}"

        repo.guardar_consentimiento(
            usuario_id=usuario_id,
            organizacion_id="org-123",
            consentimiento_otorgado=True,
        )

        result = repo.obtener_consentimiento_mas_reciente(usuario_id)
        assert result is True

    def test_obtener_consentimiento_mas_reciente_false(self, db: Session):
        """Obtener consentimiento más reciente: False (revocación)."""
        repo = MySQLAsistenteConsentimientoRepository(db)
        usuario_id = f"user-{uuid.uuid4()}"

        # Primero otorgar
        repo.guardar_consentimiento(
            usuario_id=usuario_id,
            organizacion_id="org-123",
            consentimiento_otorgado=True,
        )

        # Luego revocar
        repo.guardar_consentimiento(
            usuario_id=usuario_id,
            organizacion_id="org-123",
            consentimiento_otorgado=False,
        )

        result = repo.obtener_consentimiento_mas_reciente(usuario_id)
        assert result is False

    def test_obtener_consentimiento_sin_registro_retorna_none(self, db: Session):
        """Sin registro de consentimiento: retorna None."""
        repo = MySQLAsistenteConsentimientoRepository(db)
        result = repo.obtener_consentimiento_mas_reciente("user-inexistente")
        assert result is None

    def test_listar_consentimientos_organizacion(self, db: Session):
        """Listar consentimientos de una organización."""
        repo = MySQLAsistenteConsentimientoRepository(db)
        org_id = f"org-{uuid.uuid4()}"

        for i in range(3):
            repo.guardar_consentimiento(
                usuario_id=f"user-{i}",
                organizacion_id=org_id,
                consentimiento_otorgado=i % 2 == 0,
            )

        results = repo.listar_consentimientos_organizacion(org_id, limit=10)
        assert len(results) == 3
        assert all("usuario_id" in r for r in results)
        assert all("consentimiento_otorgado" in r for r in results)
        assert all("fecha" in r for r in results)

    def test_listar_consentimientos_respeta_limit(self, db: Session):
        """Listar respeta límite."""
        repo = MySQLAsistenteConsentimientoRepository(db)
        org_id = f"org-{uuid.uuid4()}"

        for i in range(5):
            repo.guardar_consentimiento(
                usuario_id=f"user-{i}",
                organizacion_id=org_id,
                consentimiento_otorgado=True,
            )

        results = repo.listar_consentimientos_organizacion(org_id, limit=2)
        assert len(results) == 2


# Helper class para testing sin necesidad de inyectar todas las dependencias
class ProcesarPreguntaUseCaseWithDependencies(ProcesarPreguntaAsistenteUseCase):
    """Alias para tests."""

    pass


# Fixtures
@pytest.fixture
def db():
    """Session de BD para tests."""
    # Este fixture debería estar configurado en conftest.py
    # Por ahora es un placeholder
    pass
