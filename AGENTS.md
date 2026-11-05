# AGENTS.md — Datamaq Telemetry

API FastAPI y Worker MQTT para la ingesta y persistencia de telemetría de medidores de energía Powermeter. Clean Architecture + DDD temático, tipado estricto, Python 3.10+ (venv local: `.venv/`, Python 3.12 = CI y producción).

## Comandos (siempre desde la raíz del repo)

- Servidor dev: `./run.sh` — activa `.venv/`, setea `PYTHONPATH=.`, corre `uvicorn src.main:app --reload` en `:8000`.
- Push y Deploy con feedback en vivo: `./push.sh` o `git push-watch` — ejecuta el Gauntlet local, hace push y transmite el estado en vivo del CI/CD en GitHub Actions (el CI en la nube corre solo en PR a `main`).
- Inspección de logs en VPS: `./scripts/logs.sh [-f | -n 200 | --status | --mqtt | --save]` — consulta y transmite logs de producción.
- Gauntlet completo (local, el mismo que corre el CI): `./scripts/ci.sh` — integridad, ruff, pyright, tests unitarios con cobertura >=85%, integración.
- Gauntlet pre-push (local): `./scripts/pre-push.sh` — etapas 1-4 (sin integración).
- Hook de git: `git config core.hooksPath .githooks` (una vez por clonado; invoca `scripts/pre-push.sh` en cada push).
- Tests unitarios: `.venv/bin/pytest tests/unit/` (agregar `-n auto` para usar todos los núcleos: 57 s → 24 s en 8 cores; un archivo suelto conviene correrlo sin `-n`, el arranque de los workers cuesta ~2 s).
- Verificación de arquitectura y tamaño: `.venv/bin/python scripts/verify_architecture.py && .venv/bin/python scripts/verify_code_size.py`
- Linter: `.venv/bin/ruff check .`
- LSP de OpenCode: habilitado vía `opencode.json` (servidor `pyright` → `.venv/bin/pyright-langserver --stdio`); da feedback de diagnósticos de tipos de `src/` al agente. La verificación autoritativa de tipos sigue siendo `.venv/bin/pyright` (etapa 3 del Gauntlet).
- **`gh` en este repo:** el remoto es SSH y `gh` sin `-R` falla con «none of the git remotes ... known GitHub host». Usar siempre `gh <cmd> -R datamaq-automation/datamaq-telemetry`. `gh run watch --exit-status` no es confiable como verificación: confirmar con `gh run list` después.

## CI/CD (decisión 2026-10-27: CI solo en PR a `main`)

- **`develop` se valida en local:** correr `APP_ENV=test ./scripts/pre-push.sh` (o `./scripts/ci.sh` para el gauntlet completo) antes de cada push. El PR a `develop` se abre igual, lleva el resumen del gauntlet local en el cuerpo y se mergea sin CI.
- **CI en la nube (`ci.yml`) corre solo en PR hacia `main`.** Los push y PR a `develop` no disparan workflows.
- **CD de producción (`deploy.yml`)** se dispara con el push a `main` o a mano (`workflow_dispatch`) sobre `main`. No vuelve a correr el gauntlet: no se mergea a `main` un PR con CI rojo o sin terminar (verificar `gh pr checks`).
- **Staging (`deploy-staging.yml`)** se despliega a mano (`workflow_dispatch`), siempre desde `develop`, una vez por tanda de cambios. Verificar `/health/build`.
- **CI Nightly (`ci-nightly.yml`)** es solo manual (`workflow_dispatch`), antes de actualizar dependencias.
- Decisión completa: `decisions/2026-10-27_ci-solo-en-pr-a-main.md` (repo padre).

## Entornos (Development vs Producción)

**Dos bases de datos completamente separadas:**
- **Desarrollo/Testing (127.0.0.1:3306, `.env` local):** Vacía salvo por fixtures. Usada por tests locales y `./run.sh`.
- **Producción (VPS, acceso via `ssh vps`):** Datos reales desde 2026-09. Script: `./scripts/logs.sh` (solo lectura de logs). Para queries SQL directas: `ssh vps` → `mysql -u ... -p...` (credenciales en VPS).

**Regla:** Antes de queryar datos históricos/reales de medidores, validar: ¿esto es fixture de test (dev) o datos de producción? Si es producción, usar `ssh vps`.

## Datos maestros (`data/`, repo `datamaq-data`)

- **Cambios que tocan valores testeados:** un cambio en `datamaq-data` que toque un valor testeado (`correccion_angular_fases`, `potencia_contratada`, etc.) debe actualizar en el mismo flujo los tests que lo hardcodean (`tests/unit/test_yaml_organizaciones_repository.py`, `tests/unit/test_nodo_unifilar_potencia_contratada.py`). Si no, el CI de `main` queda en rojo.
- **Despliegue de datos en el VPS:** el pull `--ff-only` trae todo `origin/main` de `datamaq-data`, no solo el commit propio. Antes de pullear, revisar `git log origin/main` contra el VPS. El pull no recarga el servicio: un cambio de datos necesita reinicio para que el proceso lo tome, con autorización explícita.

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

## Comunicación con Sesión Padre Orquestadora (el padre, ver `ListAgents`)

**TODA respuesta, cierre de tarea o reporte de bloqueadores DEBE dirigirse al PADRE, no al dueño.**

**Protocolo (obligatorio):**
1. Carga la herramienta `SendMessage` (si está deferred, usa `ToolSearch("select:SendMessage")`)
2. Envía mensaje al padre (ver `ListAgents`):
   ```
   SendMessage(to="<nombre del padre (ver ListAgents)>", 
     summary="[Resumen corto de lo que reportas]",
     message="[Detalle completo del cierre / bloqueador / status]")
   ```
3. Verifica que el resultado diga `"success":true`

**Ejemplos:**
```
✅ Correcto:
SendMessage(to="<nombre del padre (ver ListAgents)>", 
  summary="Trazabilidad TI Bloque A ✅",
  message="T1–T5 commiteado en feat/trazabilidad-cambios-ti. Gauntlet pasó, integración en deploy-server.sh pendiente.")

❌ Incorrecto:
"Completé la tarea" (sin SendMessage → va a dueño)
SendMessage(to="agustin", ...) (envío directo al dueño, saltándose padre)
```

**Criterio: ¿a quién reportar?**
- **Padre (el padre, ver `ListAgents`):** Status de tarea, cierre de bloque, bloqueadores técnicos, coordinaciones con otros repos
- **Dueño:** Solo si padre te pide que plantees pregunta de negocio al dueño explícitamente

---

## Cuando Tengas Dudas o Preguntas

**SIEMPRE indicar explícitamente:**
```
📋 PREGUNTA PARA: [Sesión Padre | Dueño]
```

**Criterio:**
- **Sesión Padre:** Ambigüedad en briefing, inconsistencias YAML↔DB, bloqueos transversales
  - Usar SendMessage: `SendMessage(to="<nombre del padre (ver ListAgents)>", summary="Pregunta", message="...")`
- **Dueño:** Clarificación de negocio, detalles técnicos de este repo que padre no puede responder
  - Padre te indicará explícitamente si traspasar pregunta al dueño

Ver `memory/clarificar-destinatario-preguntas.md` para tabla de criterios.

## Optimización de Tokens y Hardware Local (CPU, RAM, iGPU)

- **Hardware Local Primero ($0 tokens):** Aprovechar la CPU Ryzen multi-hilo, 32GB RAM e iGPU para realizar el trabajo pesado (AST, linters, tests) antes y después de interactuar con el modelo.
- **Poda AST de Contexto Obligatoria:** Prohibido leer archivos completos >100 líneas con `view_file` sin acotar (`StartLine`/`EndLine` ≤ 150). Usar poda AST local:
  `python3 /home/agustin/.agents/skills/token-optimizer/scripts/prune_python_ast.py <archivo.py>`
- **Herramientas MCP Locales:** Usar `tokenix-filter` (`tokenix_read`, `tokenix_symbols`, `tokenix_callers`) y `codebase-memory` (`search_graph`, `get_code_snippet`) para navegar código con mínimo consumo de tokens.
- **Auto-reparación Local en CPU:** Ejecutar `ruff check --fix && ruff format` y `pytest` en local antes de pedir correcciones al modelo remoto.
- **Diffs Quirúrgicos:** Usar `replace_file_content` con bloques mínimos de contexto (2-3 líneas).
- **Orquestador `agy-opt`:** Utilizar utilidades de `agy-opt` (`agy-opt inject`, `agy-opt heal`, `agy-opt stats`) para acelerar el desarrollo.
