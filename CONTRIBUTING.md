# Contribuir a datamaq-telemetry

## Ramas y flujo de integración

1. Crear una rama temática desde `develop`: `feat/...`, `fix/...`, `chore/...`, `docs/...`.
2. Commits atómicos por capa, en Conventional Commits y en español. El cuerpo explica el porqué.
3. Antes de pushear, correr el gauntlet local en verde:
   - `APP_ENV=test ./scripts/pre-push.sh` (etapas 1-4: integridad, ruff, pyright, unit + cobertura).
   - `./scripts/ci.sh` para el gauntlet completo (agrega integración).
4. Abrir el PR hacia `develop` con el resumen del gauntlet local en el cuerpo. Se mergea sin CI en la nube.
   La plantilla de PR es la del repo padre (`datamaq-automation/datamaq`, `.github/PULL_REQUEST_TEMPLATE.md`). Este repo no tiene una propia.
5. Release: abrir el PR `develop` → `main`. Ese PR corre el CI en la nube; se mergea solo con el CI en verde
   (verificar con `gh pr checks`). El merge a `main` dispara el CD de producción.

## CI/CD (decisión 2026-10-27: CI solo en PR a `main`)

| Workflow | Disparador | Qué hace |
|---|---|---|
| `ci.yml` | `pull_request` a `main` | Gauntlet completo (integridad, ruff, pyright, unit con cobertura ≥ 85 %, integración) |
| `deploy.yml` | `push` a `main` + `workflow_dispatch` | Deploy a producción (api, 8885) con verificación de `/health/build` y rollback |
| `deploy-staging.yml` | `workflow_dispatch` | Deploy a staging (api-dev, 8886) desde `develop` |
| `ci-nightly.yml` | `workflow_dispatch` | Gauntlet con dependencias frescas, antes de actualizar dependencias |

- `develop` se valida en local: los push y PR a `develop` no consumen minutos de Actions.
- Staging y el nightly son manuales: staging una vez por tanda de cambios; el nightly antes de actualizar
  dependencias.
- No se mergea a `main` un PR con el CI en rojo o sin terminar.

Decisión completa: `decisions/2026-10-27_ci-solo-en-pr-a-main.md` (repo padre).

## Requisitos de calidad

- `ruff check .` y `ruff format --check .` sin errores ni warnings.
- `pyright` sin diagnósticos (configuración estricta del repo).
- Tests unitarios con cobertura ≥ 85 % y tests de integración en verde.
- Los `__init__.py` de `src/` y `tests/` quedan en 0 bytes.
- Imports absolutos (`from src....`), nunca relativos.
