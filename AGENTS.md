# AGENTS.md — Datamaq Telemetry

API FastAPI y Worker MQTT para la ingesta y persistencia de telemetría de medidores de energía Powermeter. Clean Architecture + DDD temático, tipado estricto, Python 3.10+ (venv local: `venv/`).

## Comandos (siempre desde la raíz del repo)

- Servidor dev: `./run.sh` — activa `venv/`, setea `PYTHONPATH=.`, corre `uvicorn src.main:app --reload` en `:8000`.
- Tests unitarios: `venv/bin/pytest tests/unit/`
- Verificación de arquitectura: `venv/bin/python scripts/verify_architecture.py`
- Linter: `venv/bin/ruff check .`

## Reglas de Dependencia y Arquitectura

- `src/domain/{tematica}/` — `entities.py`, `value_objects.py`, `services.py`, `ports.py`, `exceptions.py`. Dominio 100% puro: solo stdlib + `@dataclass(frozen=True)`; **prohibido importar librerías de terceros**.
- `src/application/` — `dtos/` (Pydantic v2), `mappers/`, `use_cases/`. Solo importa de `domain/`.
- `src/adapters/` — `controllers/`, `gateways/`, `presenters/`.
  - **Inversión de Dependencias:** Nunca importa `src/infrastructure/`.
  - **Agnosticismo Web:** Controladores y presenters son clases puras de Python agnósticas de frameworks web.
- `src/infrastructure/` — organizado por librería: `fastapi/`, `sqlalchemy/`, `paho_mqtt/`, `pydantic/`.
- `src/main.py` — Entrypoint ASGI (`app = create_app()`).

## Convenciones

- **Imports absolutos `from src....` — nunca relativos.**
- **Todos los `__init__.py` (`src/` y `tests/`) deben ser de 0 bytes.**
- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
