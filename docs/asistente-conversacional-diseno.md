# Asistente Conversacional (Chatbot) — Diseño Conceptual

> **Estado:** Documento de diseño conceptual. No describe código existente ni un plan de
> implementación cerrado — es la base de razonamiento para una futura sesión de implementación.
> **Origen:** Sesión de diseño 2026-09-12, a partir del pedido de incorporar un canal de
> comunicación conversacional dentro de la app, donde el usuario pueda preguntar "qué está
> pasando" y recibir una explicación en lenguaje natural de su propia telemetría, alertas,
> disponibilidad y cargas.

---

## 1. Objetivo y alcance

Agregar un chatbot dentro de la app que explique en lenguaje natural el estado de la planta del
usuario logueado: qué está pasando ahora mismo, qué alertas hay activas, cómo viene la
disponibilidad de las máquinas y el consumo por carga. El chatbot **debe ver únicamente los datos
de la organización a la que pertenece el usuario que inició sesión** — el mismo aislamiento
multi-tenant que ya rige el resto de la plataforma.

Este documento no define todavía el esquema exacto de tablas nuevas ni el contrato de API — es
intencionalmente conceptual, para alinear criterio (y, sobre todo, la restricción de hardware)
antes de comprometer un diseño técnico.

---

## 2. Restricción de partida: sin GPU en el VPS

A diferencia de otras decisiones de este documento, esta **no es una preferencia de diseño, es una
restricción física**: el VPS de producción no tiene GPU. Eso descarta correr un LLM conversacional
de calidad aceptable en el propio servidor:

- Modelos chicos cuantizados (3-7B) en CPU pueden generar texto, pero en este dominio el riesgo de
  error es alto — alucinar una cifra de potencia o confundir kW con kVAr es un error peligroso, no
  cosmético. La correctitud numérica importa más que en un chatbot genérico.
- La latencia de generación en CPU (varios segundos a decenas de segundos por respuesta) es
  incompatible con el requisito de streaming en vivo.

**Decisión resultante:** dividir el trabajo en dos partes con costos muy distintos:

1. **Clasificación de intención** (¿qué está preguntando el usuario?) — corre local, en CPU, con
   un modelo de embeddings chico. Es barato, rápido y no necesita salir a internet.
2. **Generación de la explicación en lenguaje natural** — se delega a **Groq** (inferencia
   hospedada, ya con API key disponible), que sí puede dar la latencia de streaming que se busca.

---

## 3. Punto de partida: qué ya existe en la plataforma y se puede reusar

- **Aislamiento multi-tenant ya resuelto.** `src/infrastructure/fastapi/auth_dependencies.py` ya
  resuelve el usuario autenticado y su `organizacion_id` desde la cookie `datamaq_token` en cada
  request/WebSocket. `src/domain/telemetria/servicios/aislamiento_broadcast.py` aplica el mismo
  filtro en tiempo real. El chatbot no necesita (ni debe) implementar su propio mecanismo de
  aislamiento — reusa el existente.
- **Los datos que el chatbot va a explicar ya están modelados y expuestos** vía casos de uso
  existentes: telemetría instantánea/energía, alertas (`device_alerts`), disponibilidad
  (`machine_availability_events`, `ParadaProgramada`) y cargas (`loads`,
  `load_activity_intervals`). El chatbot debe **leer** estos datos a través de los use cases ya
  filtrados por organización, no re-implementar queries propias.
- **Clean Architecture vigente y con Guantelete de Restricciones automatizado**
  (`tests/test_architecture.py`, 9 baterías AST). Cualquier código nuevo debe entrar como un
  bounded context más, respetando la regla de dependencia de capas.

---

## 4. Certezas

1. **El filtro por organización va en el código, no en el prompt del LLM.** El controller resuelve
   `organizacion_id` desde la sesión autenticada (igual que cualquier endpoint actual) y se lo pasa
   al caso de uso; ni el clasificador de intención ni Groq deciden ni ven ese dato salvo lo que el
   caso de uso les entregue ya filtrado. Un LLM no es un mecanismo de control de acceso confiable.
2. **La generación de texto no puede correr en el VPS sin GPU con calidad/latencia aceptables** —
   ver sección 2. Esto no es negociable con hardware actual; si en el futuro cambia (GPU dedicada,
   o se decide pagar Claude/otro proveedor hospedado), el punto de extensión es el adapter de
   `GeneradorRespuestaPort`, no el resto del diseño.
3. **La clasificación de intención sí puede (y conviene que) corra local en CPU** — es una tarea de
   comprensión acotada (mapear una pregunta a un conjunto cerrado de intenciones/tools), no de
   generación abierta, y un modelo de embeddings chico (ej. `all-MiniLM-L6-v2` o similar vía
   `sentence-transformers`/sistemas de inferencia CPU como `fastembed`) resuelve esto con latencia
   de milisegundos y sin costo por token.
4. **El chatbot no debe inventar cifras.** El texto que genera Groq debe construirse a partir de un
   contexto ya armado con números reales sacados de la base (vía los use cases existentes), nunca
   a partir de que el LLM "recuerde" o infiera un valor de telemetría.
5. **Encaja como un bounded context nuevo** (`src/domain/asistente/`), con dos puertos de dominio
   (`ClasificadorIntencionPort`, `GeneradorRespuestaPort`) y dos adapters de infraestructura
   (embeddings local, Groq), sin tocar la arquitectura de los bounded contexts existentes —
   `telemetria`, `disponibilidad`, `cargas`, `sge` se consumen desde el caso de uso del asistente
   como colaboradores, no se modifican.
6. **El streaming en vivo requiere WebSocket o SSE**, no un endpoint REST tradicional — el patrón
   ya existe en el proyecto para `/ws/live`, así que el mecanismo de transporte no es nuevo, solo
   el contenido que viaja por él.

---

## 5. Dudas abiertas (a relevar antes de comprometer diseño técnico)

| # | Duda | Por qué importa |
|---|---|---|
| 1 | ¿Catálogo cerrado de intenciones (ej. "alertas activas", "consumo actual", "disponibilidad de máquina X", "comparar con ayer") o debe soportar preguntas libres desde el día uno? | Define la complejidad del clasificador de intención y cuántas "tools" de contexto hay que construir en la primera iteración. |
| 2 | ¿Qué pasa cuando el clasificador de embeddings no reconoce la intención con confianza suficiente? ¿Responder "no entendí", pedir aclaración, o mandar la pregunta cruda a Groq igual (con menos contexto estructurado)? | Afecta la experiencia de usuario y el riesgo de que Groq responda sin datos reales de respaldo. |
| 3 | ¿Groq recibe *tool calling* (decide qué datos pedir) o el caso de uso arma un contexto fijo según la intención ya clasificada y se lo pasa como texto? | Tool calling es más flexible pero más difícil de auditar; contexto fijo es más simple y más fácil de garantizar que no se filtra información fuera de la organización. |
| 4 | ¿Qué modelo de Groq (Llama, etc.) y con qué política de reintento si Groq está caído o rate-limiteado? | Define UX de fallback (¿mensaje de error simple? ¿degradar a una respuesta armada sin LLM con los mismos datos en formato tabla?). |
| 5 | ¿El historial de conversación se persiste (para contexto multi-turno) o cada pregunta es independiente? | Persistir requiere una tabla nueva y decisiones de retención/privacidad; no persistir simplifica pero pierde continuidad ("¿y ayer?"). |
| 6 | ¿Qué logging/auditoría se necesita sobre las preguntas y respuestas del chatbot (para revisar calidad, detectar alucinaciones, o por requisitos de la organización)? | Relevante sobre todo si en algún momento se usa esto para decisiones operativas, no solo informativas. |
| 7 | ¿Rate limiting propio del endpoint del asistente, separado del rate limiting general de la API? | Cada pregunta al asistente cuesta dinero (Groq) a diferencia de un GET normal — conviene no dejarlo con el mismo límite que el resto. |
| 8 | ¿Quién ve el chatbot — todos los roles (`admin`, `operador`, `invitado`) o se restringe a ciertos roles? | El invitado ya tiene acceso stateless limitado (`/guest`); hay que decidir si aplica la misma limitación al asistente. |
| 9 | ¿Conviene versionar/testear el prompt del sistema del asistente con un eval set (para detectar regresiones cuando se ajuste), o queda fuera de alcance de la primera iteración? | Afecta si se arma infraestructura de evaluación desde el principio o se pospone. |

---

## 6. Notas de implementación (para cuando se aterrice el diseño técnico)

- **No mezclar SDKs:** si se usa el SDK de Groq (compatible con la interfaz de OpenAI) o llamadas
  HTTP directas, mantenerlo aislado en `src/infrastructure/groq/` — el dominio y la aplicación
  nunca deben importar el SDK del proveedor directamente (regla de capas del Guantelete).
- **`GROQ_API_KEY` centralizada en `Settings`** (`src/infrastructure/settings/config.py`), nunca
  como variable de entorno leída directamente fuera de ahí (bateria `test_no_os_environ_direct_access`
  ya vigente en `tests/test_architecture.py`).
- El adapter de embeddings local puede sumar una dependencia nueva al proyecto
  (`sentence-transformers` o `fastembed`) — vale la pena medir el tamaño del modelo descargado y el
  tiempo de arranque en frío del proceso, ya que corre en el mismo VPS que sirve la API.
