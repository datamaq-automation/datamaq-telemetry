# Apagar el bot conversacional hasta aislarlo por organización (OWASP A01)

## 1. Objetivo y Contexto

Copiado del bloque `Repo: datamaq-telemetry` de `specs/bot-conversacional-aislamiento.md` del repo
padre. Decisión: `decisions/2026-09-24_bot-conversacional-aislamiento.md` (D1–D3 aprobadas).

**Objetivo:** que ningún endpoint de chat devuelva datos de otra organización ni respuestas
inventadas.

Certezas (verificadas en `6d857e5`):
- `routes/asistente_router.py` (`POST /api/v1/asistente/preguntar`) y `routes/copilot_router.py`
  (`POST /api/v1/copilot/chat`) leen `user_claims.get("organizacion_id")`, pero el JWT emite `org`
  (`jwt_token_service.py:48`): siempre llega `""`.
- Con `""`, `dispositivos_repository.listar` no filtra (`if organizacion_id:`): el asistente recibe los
  medidores de todas las organizaciones. `listar_alertas(solo_abiertas=True, limite=20)` no filtra por
  organización. Sin clave de Groq, el "modo simulación" devuelve `contexto[:500]` crudo.
- `copilot` responde datos inventados.
- La SPA no llama a ninguno de los dos endpoints.

**Entregas:**
1. Apagado (deploy propio): quitar `asistente_router` y `copilot_router` de `create_app`.
2. Arreglo del asistente antes de reencender: claim `org`; fallar cerrado sin organización y sin rol
   global; alertas filtradas por organización; el modo simulación no devuelve el contexto crudo;
   tests de aislamiento.
3. Borrar `copilot`: router, caso de uso, DTOs, dependencia y tests.

**Fuera de alcance:** reencender con clave de Groq (pendiente de la decisión de privacidad del dueño).

## 2. Dominio & Puertos

Entrega 1: sin cambios. Entrega 2: `GestionarAlertasUseCase.listar_alertas` recibe la organización;
el filtro se resuelve en infraestructura (alerta → dispositivo → planta → organización del YAML).

## 3. Caso de uso & DTOs

- Entrega 1: `create_app` no registra los dos routers; los módulos siguen existiendo para la entrega 2.
- Entrega 2: el router resuelve `organizacion_id` como `planta_ownership.py` (claims `rol`/`org`,
  roles globales → `None`); rol no global sin `org` → 404 sin llamar al caso de uso.
  `ProcesarPreguntaAsistenteUseCase` pasa la organización a dispositivos y alertas.
  `GroqRespuestaAdapter` sin clave responde un texto fijo sin datos del contexto.

## 4. Matriz de Pruebas (RED Suite)

- Entrega 1 — `test_chat_apagado.py`: `POST /api/v1/asistente/preguntar` y `/api/v1/copilot/chat` → 404.
- Entrega 2 — usuario de org A: el contexto armado no contiene medidores ni alertas de B; sin `org` y
  rol no global → 404; modo simulación sin datos del contexto.

## 5. Criterios del Gauntlet

- `venv/bin/ruff check .`, `venv/bin/ruff format --check .`, `venv/bin/python -m pyright` sin errores.
- `venv/bin/python -m pytest tests/unit -n auto --cov=src --cov-fail-under=85` en verde, también con
  MySQL inalcanzable (`DB_HOST=127.0.0.2 DB_PORT=1`), como en CI.
- `scripts/verify_architecture.py` y `scripts/verify_code_size.py`.
