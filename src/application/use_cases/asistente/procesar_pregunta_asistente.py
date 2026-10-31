"""src/application/use_cases/asistente/procesar_pregunta_asistente.py."""

import json
import logging
import uuid
from typing import ClassVar

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.application.use_cases.asistente.recopilar_telemetria import (
    recopilar_telemetria,
)
from src.application.use_cases.consultar_telemetria import (
    ConsultarTelemetriaUseCase,
)
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_dispositivos import (
    GestionarDispositivosUseCase,
)
from src.domain.asistente.entities import (
    ConversacionAsistente,
    IntencionClasificada,
    MensajeAsistente,
    RegistroClasificacionIntencion,
    RespuestaAsistente,
)
from src.domain.asistente.ports import (
    ClasificadorIntencionPort,
    GeneradorRespuestaPort,
    RepositorioConversacionesAsistentePort,
)
from src.domain.asistente.value_objects import (
    ContextoPreguntaAsistente,
    IntencionUsuario,
)

logger = logging.getLogger(__name__)


class ProcesarPreguntaAsistenteUseCase:
    """Procesa preguntas y recopila contexto dentro de la organización."""

    _intencion_mapeo: ClassVar[dict[str, IntencionUsuario]] = {
        "EXPLICAR_ALERTAS": IntencionUsuario.EXPLICAR_ALERTAS,
        "SALUD_DISPOSITIVOS": IntencionUsuario.SALUD_DISPOSITIVOS,
        "RESUMEN_TELEMETRIA": IntencionUsuario.RESUMEN_TELEMETRIA,
    }

    def __init__(
        self,
        clasificador: ClasificadorIntencionPort,
        generador: GeneradorRespuestaPort,
        repo_conversaciones: RepositorioConversacionesAsistentePort,
        gestor_alertas: GestionarAlertasUseCase,
        gestor_dispositivos: GestionarDispositivosUseCase,
        consultar_telemetria: ConsultarTelemetriaUseCase | None = None,
    ) -> None:
        self._clasificador = clasificador
        self._generador = generador
        self._repo_conversaciones = repo_conversaciones
        self._gestor_alertas = gestor_alertas
        self._gestor_dispositivos = gestor_dispositivos
        self._consultar_telemetria = consultar_telemetria

    def _construir_prompt_contexto(
        self,
        contexto: ContextoPreguntaAsistente,
    ) -> str:
        payload = {
            "organizacion_id": contexto.organizacion_id,
            "intencion_detectada": contexto.intencion.value,
            "alertas_recientes": contexto.datos_alertas or [],
            "estado_dispositivos": contexto.datos_dispositivos or [],
            "telemetria": contexto.datos_telemetria or {},
        }
        return (
            "Eres el asistente oficial de DataMaq Telemetry. "
            "Explica al usuario en español técnico pero claro la situación "
            "operativa de su planta. "
            "REGLA INVIOLABLE: Utiliza ÚNICAMENTE los datos reales provistos "
            "en el siguiente JSON de contexto. "
            "NO inventes valores numéricos, horas ni métricas de señal que "
            "no estén explícitamente detallados.\n\n"
            f"DATOS DE CONTEXTO REALES:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"PREGUNTA DEL USUARIO: {contexto.pregunta}"
        )

    def _recopilar_datos(
        self,
        intencion: IntencionUsuario,
        organizacion_id: str,
    ) -> tuple[list[dict], list[dict]]:
        """Recopila alertas abiertas y dispositivos de la organización."""
        if intencion not in (
            IntencionUsuario.EXPLICAR_ALERTAS,
            IntencionUsuario.SALUD_DISPOSITIVOS,
        ):
            return [], []

        alertas: list[AlertaResponseDTO] = self._gestor_alertas.listar_alertas(
            solo_abiertas=True,
            limite=20,
            organizacion_id=organizacion_id,
        )
        dispositivos: list[DispositivoResponseDTO] = self._gestor_dispositivos.listar_dispositivos(
            organizacion_id=organizacion_id,
        )
        return (
            [alerta.model_dump(mode="json") for alerta in alertas],
            [dispositivo.model_dump(mode="json") for dispositivo in dispositivos],
        )

    def _recopilar_telemetria(
        self,
        intencion: IntencionUsuario,
        organizacion_id: str,
    ) -> dict:
        return recopilar_telemetria(
            intencion=intencion,
            organizacion_id=organizacion_id,
            gestor_dispositivos=self._gestor_dispositivos,
            consultar_telemetria=self._consultar_telemetria,
        )

    def _obtener_o_crear_conversacion(
        self,
        conversacion_id: str | None,
        organizacion_id: str,
        usuario_id: str,
    ) -> ConversacionAsistente:
        if conversacion_id:
            conversacion = self._repo_conversaciones.obtener_conversacion(
                conversacion_id,
                organizacion_id,
            )
            if conversacion is not None:
                return conversacion

        return self._repo_conversaciones.crear_conversacion(
            organizacion_id,
            usuario_id,
        )

    def _generar_texto_respuesta(
        self,
        pregunta: str,
        prompt: str,
        datos_alertas: list[dict],
        datos_dispositivos: list[dict],
        usuario_consiente_envio_groq: bool,
    ) -> tuple[str, bool, bool, str | None]:
        if usuario_consiente_envio_groq:
            iterador_respuesta = self._generador.generar(pregunta, prompt)
            return "".join(list(iterador_respuesta)), False, True, None

        texto_respuesta = (
            "Nota: Esta respuesta es local (sin IA remota). "
            f"Tienes {len(datos_alertas)} alerta(s) abierta(s) "
            f"y {len(datos_dispositivos)} dispositivo(s) conectado(s). "
            "Para una respuesta más completa, autoriza el uso de IA remota "
            "en tu perfil."
        )
        return texto_respuesta, True, False, "sin_consentimiento"

    def _persistir_interaccion(
        self,
        conversacion_id: str,
        organizacion_id: str,
        pregunta: str,
        texto_respuesta: str,
        clasificacion: IntencionClasificada,
    ) -> None:
        mensaje_usuario = MensajeAsistente(
            id=str(uuid.uuid4()),
            conversacion_id=conversacion_id,
            rol="usuario",
            texto=pregunta,
        )
        self._repo_conversaciones.guardar_mensaje(
            mensaje_usuario,
            organizacion_id,
        )

        mensaje_asistente = MensajeAsistente(
            id=str(uuid.uuid4()),
            conversacion_id=conversacion_id,
            rol="asistente",
            texto=texto_respuesta,
        )
        self._repo_conversaciones.guardar_mensaje(
            mensaje_asistente,
            organizacion_id,
        )

        registro = RegistroClasificacionIntencion(
            id=str(uuid.uuid4()),
            mensaje_id=mensaje_usuario.id,
            intencion=clasificacion,
        )
        self._repo_conversaciones.guardar_clasificacion(
            registro,
            organizacion_id,
        )

    def ejecutar(
        self,
        pregunta: str,
        organizacion_id: str,
        usuario_id: str,
        conversacion_id: str | None = None,
        usuario_consiente_envio_groq: bool = False,
    ) -> RespuestaAsistente:
        if not organizacion_id:
            raise ValueError("El asistente requiere la organización del usuario.")

        conversacion = self._obtener_o_crear_conversacion(
            conversacion_id,
            organizacion_id,
            usuario_id,
        )

        clasificacion = self._clasificador.clasificar(pregunta)
        intencion = self._intencion_mapeo.get(
            clasificacion.nombre,
            IntencionUsuario.DESCONOCIDO,
        )

        datos_alertas, datos_dispositivos = self._recopilar_datos(
            intencion,
            organizacion_id,
        )
        datos_telemetria = self._recopilar_telemetria(
            intencion,
            organizacion_id,
        )

        contexto = ContextoPreguntaAsistente(
            organizacion_id=organizacion_id,
            pregunta=pregunta,
            intencion=intencion,
            datos_alertas=datos_alertas,
            datos_dispositivos=datos_dispositivos,
            datos_telemetria=datos_telemetria,
        )
        prompt = self._construir_prompt_contexto(contexto)

        (
            texto_respuesta,
            consentimiento_requerido,
            enviado_groq,
            razon_sin_groq,
        ) = self._generar_texto_respuesta(
            pregunta,
            prompt,
            datos_alertas,
            datos_dispositivos,
            usuario_consiente_envio_groq,
        )

        self._persistir_interaccion(
            conversacion.id,
            organizacion_id,
            pregunta,
            texto_respuesta,
            clasificacion,
        )

        return RespuestaAsistente(
            texto=texto_respuesta,
            intencion=clasificacion.nombre,
            consentimiento_requerido=consentimiento_requerido,
            enviado_a_groq=enviado_groq,
            razon_sin_groq=razon_sin_groq,
        )
