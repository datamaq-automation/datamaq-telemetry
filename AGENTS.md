# AGENTS.md — Datamaq Telemetry

API FastAPI y Worker MQTT para la ingesta y persistencia de telemetría de medidores de energía Powermeter. Clean Architecture + DDD temático, tipado estricto, Python 3.10+ (venv local: `venv/`).

## Comandos (siempre desde la raíz del repo)

- Servidor dev: `./run.sh` — activa `venv/`, setea `PYTHONPATH=.`, corre `uvicorn src.main:app --reload` en `:8000`.
- Push y Deploy con feedback en vivo: `./push.sh` o `git push-watch` — ejecuta Gauntlet local, hace push y transmite el estado en vivo de CI y CD Deploy en GitHub Actions.
- Gauntlet completo (CI): `./scripts/ci.sh` — integridad, ruff, pyright, tests unitarios con cobertura >=85%, integración.
- Gauntlet pre-push (local): `./scripts/pre-push.sh` — etapas 1-4 (sin integración).
- Hook de git: `git config core.hooksPath .githooks` (una vez por clonado; invoca `scripts/pre-push.sh` en cada push).
- Tests unitarios: `venv/bin/pytest tests/unit/`
- Verificación de arquitectura: `venv/bin/python scripts/verify_architecture.py`
- Linter: `venv/bin/ruff check .`
- LSP de OpenCode: habilitado vía `opencode.json` (servidor `pyright` → `venv/bin/pyright-langserver --stdio`); da feedback de diagnósticos de tipos de `src/` al agente. La verificación autoritativa de tipos sigue siendo `venv/bin/pyright` (etapa 3 del Gauntlet).

## Reglas de Dependencia y Arquitectura

- `src/domain/{tematica}/` — `entities.py`, `value_objects.py`, `services.py`, `ports.py`, `exceptions.py`. Dominio 100% puro: solo stdlib + `@dataclass(frozen=True)`; **prohibido importar librerías de terceros**.
- `src/application/` — `dtos/` (Pydantic v2), `mappers/`, `use_cases/`. Solo importa de `domain/`.
- `src/adapters/` — `gateways/`, `presenters/`.
  - **Inversión de Dependencias:** Nunca importa `src/infrastructure/`.
  - **Agnosticismo Web:** Presenters y gateways son clases puras de Python agnósticas de frameworks web. La lógica de entrada vive en los casos de uso de `application/`; los routers de `infrastructure/fastapi/` los inyectan directamente (sin capa de controllers).
- `src/infrastructure/` — organizado por librería: `fastapi/`, `sqlalchemy/`, `paho_mqtt/`, `pydantic/`.
- `src/main.py` — Entrypoint ASGI (`app = create_app()`).

## Convenciones

- **Imports absolutos `from src....` — nunca relativos.**
- **Todos los `__init__.py` (`src/` y `tests/`) deben ser de 0 bytes.**
- **El LSP del editor (Pylance) debe alinear su exclusión con `pyrightconfig.json` vía `.vscode/settings.json` (`python.analysis.exclude`). Los `tests/` están excluidos del análisis de tipos por diseño; prohibido "corregirlos" con `cast`/`# type: ignore`.**
- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
