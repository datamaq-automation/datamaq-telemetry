# AGENTS.md — Datamaq Telemetry

API FastAPI y Worker MQTT para la ingesta y persistencia de telemetría de medidores de energía Powermeter. Clean Architecture + DDD temático, tipado estricto, Python 3.10+ (venv local: `.venv/`, Python 3.12 = CI y producción).

## Comandos (siempre desde la raíz del repo)

- Servidor dev: `./run.sh` — activa `.venv/`, setea `PYTHONPATH=.`, corre `uvicorn src.main:app --reload` en `:8000`.
- Push y Deploy con feedback en vivo: `./push.sh` o `git push-watch` — ejecuta Gauntlet local, hace push y transmite el estado en vivo de CI y CD Deploy en GitHub Actions.
- Inspección de logs en VPS: `./scripts/logs.sh [-f | -n 200 | --status | --mqtt | --save]` — consulta y transmite logs de producción.
- Gauntlet completo (CI): `./scripts/ci.sh` — integridad, ruff, pyright, tests unitarios con cobertura >=85%, integración.
- Gauntlet pre-push (local): `./scripts/pre-push.sh` — etapas 1-4 (sin integración).
- Hook de git: `git config core.hooksPath .githooks` (una vez por clonado; invoca `scripts/pre-push.sh` en cada push).
- Tests unitarios: `.venv/bin/pytest tests/unit/` (agregar `-n auto` para usar todos los núcleos: 57 s → 24 s en 8 cores; un archivo suelto conviene correrlo sin `-n`, el arranque de los workers cuesta ~2 s).
- Verificación de arquitectura y tamaño: `.venv/bin/python scripts/verify_architecture.py && .venv/bin/python scripts/verify_code_size.py`
- Linter: `.venv/bin/ruff check .`
- LSP de OpenCode: habilitado vía `opencode.json` (servidor `pyright` → `.venv/bin/pyright-langserver --stdio`); da feedback de diagnósticos de tipos de `src/` al agente. La verificación autoritativa de tipos sigue siendo `.venv/bin/pyright` (etapa 3 del Gauntlet).

## Entornos (Development vs Producción)

**Dos bases de datos completamente separadas:**
- **Desarrollo/Testing (127.0.0.1:3306, `.env` local):** Vacía salvo por fixtures. Usada por tests locales y `./run.sh`.
- **Producción (VPS, acceso via `ssh vps`):** Datos reales desde 2026-09. Script: `./scripts/logs.sh` (solo lectura de logs). Para queries SQL directas: `ssh vps` → `mysql -u ... -p...` (credenciales en VPS).

**Regla:** Antes de queryar datos históricos/reales de medidores, validar: ¿esto es fixture de test (dev) o datos de producción? Si es producción, usar `ssh vps`.

## Mapeo de IDs: YAML vs Base de Datos

**YAML usa IDs lógicos (números o nombres); DB usa UUIDs.** No confundir. Ver tabla completa en `docs/topologia-medidores.md`.

**Importante:**
- **Las facturas se cargan a nivel PLANTA, NO dispositivo.** Una planta puede tener múltiples distribuidoras (no son opciones mutuamente excluyentes).
- `device_uid` es el identificador MAC (ej. `EC:C9:FF:B5:7F:20`), puede variar en formato entre YAML y DB
- Siempre validar consistencia: `python scripts/validate_topology.py`
- Para validar energía contra factura: sumar energía de TODOS los dispositivos de la planta, comparar contra factura de esa planta

**Validación automática:**
```bash
python scripts/validate_topology.py           # Verificar inconsistencias YAML ↔ DB
python scripts/validate_topology.py --strict  # Fallar en warnings
```

**Fuentes de verdad:**
- `data/organizaciones.yml` (topología, medidores, device_uid)
- `devices` en DB (device_id, last_seen_at, status)
- App viva (`https://app.datamaq.com.ar/plantas/...`) para verificación visual

## Reglas de Dependencia y Arquitectura

- `src/domain/{tematica}/` — `entities.py`, `value_objects.py`, `services.py`, `ports.py`, `exceptions.py`. Dominio 100% puro: solo stdlib + `@dataclass(frozen=True)`; **prohibido importar librerías de terceros**.
- `src/application/` — `dtos/` (Pydantic v2), `mappers/`, `use_cases/`. Solo importa de `domain/`.
- `src/adapters/` — `gateways/`, `presenters/`.
  - **Inversión de Dependencias:** Nunca importa `src/infrastructure/`.
  - **Agnosticismo Web:** Presenters y gateways son clases puras de Python agnósticas de frameworks web. La lógica de entrada vive en los casos de uso de `application/`; los routers de `infrastructure/fastapi/` los inyectan directamente (sin capa de controllers).
- `src/infrastructure/` — organizado por librería: `fastapi/`, `sqlalchemy/`, `paho_mqtt/`, `pydantic/`, `yaml/`.
- `data/` — repositorio git **independiente** (`datamaq-automation/datamaq-data`, privado), no submódulo,
  ignorado por este repo: `git clone git@github.com:datamaq-automation/datamaq-data.git data` (ver README).
  Persistencia declarativa GitOps de la jerarquía de activos industriales bajo estándar **ANSI/ISA-95** e **ISO 50001**:
  - Nivel 4 (Empresa / Tenant): `./data/organizaciones.yml` o `./data/organizaciones/{org_id}/organizacion.yml`.
  - Nivel 3 (Sitio / Frontera SGE): `.../plantas/{planta_id}/planta.yml`.
  - Nivel 2 (Área / Topología y USEs): `.../plantas/{planta_id}/unifilar.yml` y `layout.yml`.
  - Verificación en startup: Toda relación de `organization_id` en MySQL se valida contra el modelo declarativo vía `verificador_consistencia_organizaciones`.
- `src/main.py` — Entrypoint ASGI (`app = create_app()`).


## Convenciones

- **Imports absolutos `from src....` — nunca relativos.**
- **Todos los `__init__.py` (`src/` y `tests/`) deben ser de 0 bytes.**
- **El LSP del editor (Pylance) debe alinear su exclusión con `pyrightconfig.json` vía `.vscode/settings.json` (`python.analysis.exclude`). Los `tests/` están excluidos del análisis de tipos por diseño; prohibido "corregirlos" con `cast`/`# type: ignore`.**
- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- **Reportes y rutas:** Al generar reportes/documentos, siempre dar rutas absolutas completas (`/home/agustin/...`), no relativas.

## Cuando Tengas Dudas o Preguntas

**SIEMPRE indicar explícitamente:**
```
📋 PREGUNTA PARA: [Sesión Padre | Dueño]
```

**Criterio:**
- **Sesión Padre:** Ambigüedad en briefing, inconsistencias YAML↔DB, bloqueos transversales
  - Proveer: texto para copiar/pegar en reporte padre
- **Dueño:** Clarificación de negocio, detalles técnicos de este repo
  - Esperar respuesta directa aquí

Ver `memory/clarificar-destinatario-preguntas.md` para tabla de criterios.

## Optimización de Tokens y Hardware Local (CPU, RAM, iGPU)

- **Hardware Local Primero ($0 tokens):** Aprovechar la CPU Ryzen multi-hilo, 32GB RAM e iGPU para realizar el trabajo pesado (AST, linters, tests) antes y después de interactuar con el modelo.
- **Poda AST de Contexto Obligatoria:** Prohibido leer archivos completos >100 líneas con `view_file` sin acotar (`StartLine`/`EndLine` ≤ 150). Usar poda AST local:
  `python3 /home/agustin/.agents/skills/token-optimizer/scripts/prune_python_ast.py <archivo.py>`
- **Herramientas MCP Locales:** Usar `tokenix-filter` (`tokenix_read`, `tokenix_symbols`, `tokenix_callers`) y `codebase-memory` (`search_graph`, `get_code_snippet`) para navegar código con mínimo consumo de tokens.
- **Auto-reparación Local en CPU:** Ejecutar `ruff check --fix && ruff format` y `pytest` en local antes de pedir correcciones al modelo remoto.
- **Diffs Quirúrgicos:** Usar `replace_file_content` con bloques mínimos de contexto (2-3 líneas).
- **Orquestador `agy-opt`:** Utilizar utilidades de `agy-opt` (`agy-opt inject`, `agy-opt heal`, `agy-opt stats`) para acelerar el desarrollo.
