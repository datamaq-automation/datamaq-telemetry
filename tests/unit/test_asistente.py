# tests/unit/test_asistente.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.infrastructure.asistente.clasificador_reglas import (
    ClasificadorIntencionReglasAdapter,
)
from src.infrastructure.groq.groq_adapter import GroqRespuestaAdapter


def test_clasificador_intencion_reglas():
    clasificador = ClasificadorIntencionReglasAdapter()

    res1 = clasificador.clasificar("¿Por qué recibí una alerta de desconexión en el Trafo Usina?")
    assert res1.nombre == "EXPLICAR_ALERTAS"
    assert res1.confianza >= 0.8

    res2 = clasificador.clasificar("¿Cuál es la salud y estado de los medidores online?")
    assert res2.nombre == "SALUD_DISPOSITIVOS"
    assert res2.confianza >= 0.8

    res3 = clasificador.clasificar("¿Cuál es el consumo de potencia en kW actual?")
    assert res3.nombre == "RESUMEN_TELEMETRIA"
    assert res3.confianza >= 0.8

    res4 = clasificador.clasificar("Hola, ¿cómo estás?")
    assert res4.nombre == "DESCONOCIDO"


def test_procesar_pregunta_asistente_aislamiento_y_sin_alucinaciones():
    # 1. Mocks de dependencias
    clasificador = ClasificadorIntencionReglasAdapter()
    generador = GroqRespuestaAdapter(api_key="mock-key")

    repo_conv = MagicMock()
    conv_mock = MagicMock()
    conv_mock.id = "conv-123"
    repo_conv.crear_conversacion.return_value = conv_mock
    repo_conv.obtener_conversacion.return_value = conv_mock

    gestor_alertas = MagicMock()
    gestor_alertas.listar_alertas.return_value = [
        AlertaResponseDTO(
            id=1,
            dispositivo_id="dev-usina",
            tipo_alerta="CONECTIVIDAD_INESTABLE",
            severidad="WARNING",
            mensaje="⚠️ RSSI: -85 dBm (umbral: -78 dBm)",
            esta_resuelta=False,
            disparada_en=datetime.now(timezone.utc),
            categoria="CONECTIVIDAD",
        )
    ]

    gestor_dispositivos = MagicMock()
    gestor_dispositivos.listar_dispositivos.return_value = [
        DispositivoResponseDTO(
            id="dev-usina",
            device_uid="F8B3B7C0BBB0",
            nombre="Trafo Usina",
            esta_activo=True,
            estado="ONLINE",
            creado_en=datetime.now(timezone.utc),
            actualizado_en=datetime.now(timezone.utc),
        )
    ]

    use_case = ProcesarPreguntaAsistenteUseCase(
        clasificador=clasificador,
        generador=generador,
        repo_conversaciones=repo_conv,
        gestor_alertas=gestor_alertas,
        gestor_dispositivos=gestor_dispositivos,
    )

    # 2. Ejecutar consulta sobre alertas para org-durax
    pregunta = "¿Qué alerta tengo en el Trafo Usina?"
    resultado = use_case.ejecutar(
        pregunta=pregunta,
        organizacion_id="org-durax",
        usuario_id="usr-1",
    )

    # 3. Verificaciones de aislamiento y respuesta sintética
    assert resultado.intencion == "EXPLICAR_ALERTAS"
    # El modo simulación no expone el contexto: ni alertas ni medidores en el texto.
    assert "CONECTIVIDAD_INESTABLE" not in resultado.texto and "Trafo Usina" not in resultado.texto
    gestor_alertas.listar_alertas.assert_called_once_with(solo_abiertas=True, limite=20, organizacion_id="org-durax")

    # Verificar que el gestor de dispositivos fue invocado con la organizacion_id correcta del usuario
    gestor_dispositivos.listar_dispositivos.assert_called_once_with(organizacion_id="org-durax")


def test_asistente_incluye_telemetria_en_contexto():
    from types import SimpleNamespace

    clasificador = MagicMock()
    clasificador.clasificar.return_value = SimpleNamespace(
        nombre="RESUMEN_TELEMETRIA",
        confianza=0.95,
    )

    generador = MagicMock()
    generador.generar.return_value = iter(["Respuesta de prueba"])

    repo_conv = MagicMock()
    repo_conv.crear_conversacion.return_value = SimpleNamespace(id="conv-telemetria")

    dispositivo = DispositivoResponseDTO(
        id="dev-1",
        device_uid="UID-1",
        nombre="Medidor de prueba",
        esta_activo=True,
        estado="ONLINE",
        creado_en=datetime.now(timezone.utc),
        actualizado_en=datetime.now(timezone.utc),
    )

    gestor_dispositivos = MagicMock()
    gestor_dispositivos.listar_dispositivos.return_value = [dispositivo]

    lectura = SimpleNamespace(
        instantanea=SimpleNamespace(
            registrado_en=datetime.now(timezone.utc),
            potencia_activa_total_W=12500.0,
            factor_potencia_total=0.95,
            voltage_linea_V=380.0,
            thd_v_promedio_pct=2.1,
            thd_i_total_pct=4.0,
        ),
        energia=SimpleNamespace(
            net_active_energy_kwh=1250.0,
        ),
        analitica=SimpleNamespace(
            estado_fp=SimpleNamespace(value="NORMAL"),
            estado_tension=SimpleNamespace(value="NORMAL"),
        ),
    )
    consultar_telemetria = MagicMock()
    consultar_telemetria.obtener_ultima_telemetria.return_value = lectura

    use_case = ProcesarPreguntaAsistenteUseCase(
        clasificador=clasificador,
        generador=generador,
        repo_conversaciones=repo_conv,
        gestor_alertas=MagicMock(),
        gestor_dispositivos=gestor_dispositivos,
        consultar_telemetria=consultar_telemetria,
    )

    resultado = use_case.ejecutar(
        pregunta="¿Cuál es la potencia actual?",
        organizacion_id="org-prueba",
        usuario_id="usr-prueba",
        usuario_consiente_envio_groq=True,
    )

    assert resultado.texto == "Respuesta de prueba"

    gestor_dispositivos.listar_dispositivos.assert_called_once_with(organizacion_id="org-prueba")

    consultar_telemetria.obtener_ultima_telemetria.assert_called_once_with("dev-1")
    prompt_enviado = generador.generar.call_args.args[1]
    assert '"potencia_activa_kw": 12.5' in prompt_enviado


def test_clasificador_maneja_preguntas_vacias_y_ambiguas():
    clasificador = ClasificadorIntencionReglasAdapter()

    # Una pregunta vacía no debe activar ninguna intención.
    vacia = clasificador.clasificar("")
    assert vacia.nombre == "DESCONOCIDO"
    assert vacia.confianza == 0.0

    # Los espacios tampoco deben activar una intención.
    espacios = clasificador.clasificar("   ")
    assert espacios.nombre == "DESCONOCIDO"
    assert espacios.confianza == 0.0

    # Sin palabras reconocibles, la intención debe ser desconocida.
    desconocida = clasificador.clasificar("Hola, ¿cómo estás?")
    assert desconocida.nombre == "DESCONOCIDO"

    # La pregunta contiene señales de alertas y de telemetría.
    ambigua = clasificador.clasificar("Quiero consultar una alerta y la potencia")
    assert ambigua.nombre == "DESCONOCIDO"


def test_asistente_continua_si_falla_una_consulta_de_telemetria():
    from types import SimpleNamespace

    clasificador = MagicMock()
    clasificador.clasificar.return_value = SimpleNamespace(
        nombre="RESUMEN_TELEMETRIA",
        confianza=0.95,
    )

    generador = MagicMock()
    generador.generar.return_value = iter(["Respuesta sin telemetria"])

    repo_conv = MagicMock()
    repo_conv.crear_conversacion.return_value = SimpleNamespace(id="conv-error-telemetria")

    dispositivo = DispositivoResponseDTO(
        id="dev-1",
        device_uid="UID-1",
        nombre="Medidor de prueba",
        esta_activo=True,
        estado="ONLINE",
        creado_en=datetime.now(timezone.utc),
        actualizado_en=datetime.now(timezone.utc),
    )

    gestor_dispositivos = MagicMock()
    gestor_dispositivos.listar_dispositivos.return_value = [dispositivo]

    consultar_telemetria = MagicMock()
    consultar_telemetria.obtener_ultima_telemetria.side_effect = RuntimeError("Error simulado de telemetria")

    use_case = ProcesarPreguntaAsistenteUseCase(
        clasificador=clasificador,
        generador=generador,
        repo_conversaciones=repo_conv,
        gestor_alertas=MagicMock(),
        gestor_dispositivos=gestor_dispositivos,
        consultar_telemetria=consultar_telemetria,
    )

    resultado = use_case.ejecutar(
        pregunta="¿Cuál es la potencia actual?",
        organizacion_id="org-prueba",
        usuario_id="usr-prueba",
        usuario_consiente_envio_groq=True,
    )

    assert resultado.texto == "Respuesta sin telemetria"
