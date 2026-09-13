import json
import uuid
from typing import ClassVar

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.asistente.entities import (
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


class ProcesarPreguntaAsistenteUseCase:
    """Caso de uso que procesa preguntas de los usuarios en lenguaje natural,

    clasifica la intención, recopila el contexto de telemetría/alertas multi-tenant
    de forma garantizada y delega la generación al adaptador de inferencia.
    """

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
    ):
        self._clasificador = clasificador
        self._generador = generador
        self._repo_conversaciones = repo_conversaciones
        self._gestor_alertas = gestor_alertas
        self._gestor_dispositivos = gestor_dispositivos

    def _construir_prompt_contexto(
        self,
        contexto: ContextoPreguntaAsistente,
    ) -> str:
        payload = {
            "organizacion_id": contexto.organizacion_id,
            "intencion_detectada": contexto.intencion.value,
            "alertas_recientes": contexto.datos_alertas or [],
            "estado_dispositivos": contexto.datos_dispositivos or [],
        }
        return (
            "Eres el asistente oficial de DataMaq Telemetry. "
            "Explica al usuario en español técnico pero claro la situación operativa de su planta. "
            "REGLA INVIOLABLE: Utiliza ÚNICAMENTE los datos reales provistos en el siguiente JSON de contexto. "
            "NO inventes valores numéricos, horas ni métricas de señal que no estén explícitamente detallados.\n\n"
            f"DATOS DE CONTEXTO REALES:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            f"PREGUNTA DEL USUARIO: {contexto.pregunta}"
        )

    def ejecutar(
        self,
        pregunta: str,
        organizacion_id: str,
        usuario_id: str,
        conversacion_id: str | None = None,
    ) -> RespuestaAsistente:
        # 1. Obtener o crear conversación multi-tenant
        if conversacion_id:
            conv = self._repo_conversaciones.obtener_conversacion(conversacion_id, organizacion_id)
            if conv is None:
                conv = self._repo_conversaciones.crear_conversacion(organizacion_id, usuario_id)
        else:
            conv = self._repo_conversaciones.crear_conversacion(organizacion_id, usuario_id)

        # 2. Clasificar intención
        clasificacion = self._clasificador.clasificar(pregunta)
        intencion_enum = self._intencion_mapeo.get(clasificacion.nombre, IntencionUsuario.DESCONOCIDO)

        # 3. Recopilar datos reales según la intención (Aislamiento Multi-tenant)
        datos_alertas: list[dict] = []
        datos_dispositivos: list[dict] = []

        if intencion_enum in (IntencionUsuario.EXPLICAR_ALERTAS, IntencionUsuario.SALUD_DISPOSITIVOS):
            # Listar alertas activas
            alertas_dtos: list[AlertaResponseDTO] = self._gestor_alertas.listar_alertas(solo_abiertas=True, limite=20)
            datos_alertas = [a.model_dump(mode="json") for a in alertas_dtos]

            # Listar dispositivos de la organización
            dispositivos_dtos: list[DispositivoResponseDTO] = self._gestor_dispositivos.listar_dispositivos(
                organizacion_id=organizacion_id
            )
            datos_dispositivos = [d.model_dump(mode="json") for d in dispositivos_dtos]

        # 4. Construir contexto y generar respuesta
        contexto = ContextoPreguntaAsistente(
            organizacion_id=organizacion_id,
            pregunta=pregunta,
            intencion=intencion_enum,
            datos_alertas=datos_alertas,
            datos_dispositivos=datos_dispositivos,
        )

        prompt = self._construir_prompt_contexto(contexto)
        iterador_respuesta = self._generador.generar(pregunta, prompt)
        texto_respuesta = "".join(list(iterador_respuesta))

        # 5. Persistir mensajes y clasificación
        msg_user = MensajeAsistente(
            id=str(uuid.uuid4()),
            conversacion_id=conv.id,
            rol="usuario",
            texto=pregunta,
        )
        self._repo_conversaciones.guardar_mensaje(msg_user, organizacion_id)

        msg_bot = MensajeAsistente(
            id=str(uuid.uuid4()),
            conversacion_id=conv.id,
            rol="asistente",
            texto=texto_respuesta,
        )
        self._repo_conversaciones.guardar_mensaje(msg_bot, organizacion_id)

        reg_clasif = RegistroClasificacionIntencion(
            id=str(uuid.uuid4()),
            mensaje_id=msg_user.id,
            intencion=clasificacion,
        )
        self._repo_conversaciones.guardar_clasificacion(reg_clasif, organizacion_id)

        return RespuestaAsistente(
            texto=texto_respuesta,
            intencion=clasificacion.nombre,
        )
