# Spec — Modos de Entorno (configuracion-entornos)

## 1. Objetivo y Contexto

Formaliza el modo de ejecución del backend en un perfil de entorno único (`APP_ENV`) con defaults coherentes por perfil, manteniendo la postura segura por defecto. Hoy `DEBUG` es un flag suelto que actúa como proxy de "desarrollo", mientras `CORS_ORIGINS`, `API_EXPOSE_DOCS`, `LOG_FORMAT` y `LOG_LEVEL` se configuran a mano por `.env`.

**Decisión de compatibilidad (refinamiento sobre la propuesta inicial):** el código existente (`.env` con `DEBUG=True` y ~30 fixtures de tests) usa `DEBUG=True` como opt-in canónico de desarrollo. Por ello, en lugar de lanzar `ValueError` ante `APP_ENV=production` + `DEBUG=True` (lo que rompería el arranque actual y decenas de tests), se adopta **coacción**: `DEBUG=True` fuerza `APP_ENV=development`. El fail-safe se preserva por otra vía: por defecto `APP_ENV=production`, y en producción se exige secreto fuerte (`validar_postura_seguridad` existente).

## 2. Dominio y Puertos

Sin cambios en `domain/` ni `application/`. Los modos son un concepto exclusivo de **Infrastructure/settings** (config) y del composition root. La regla DIP ya vigente (capas internas no importan `infrastructure.settings`) se refuerza con un test de regresión.

## 3. Casos de Uso y DTOs

Sin cambios en DTOs ni use cases.

## 4. Infraestructura

- `Settings.APP_ENV: Literal["development", "production", "test"] = "production"`.
- `DEBUG`, `API_EXPOSE_DOCS`, `CORS_ORIGINS`, `LOG_FORMAT`, `LOG_LEVEL` pasan a sentinel `None` (no especificado) y se **derivan** del perfil efectivo:
  | Campo | production | development/test |
  |---|---|---|
  | `DEBUG` | `False` | `True` |
  | `LOG_FORMAT` | `json` | `console` |
  | `LOG_LEVEL` | `INFO` | `DEBUG` |
  | `API_EXPOSE_DOCS` | `False` | `True` |
  | `CORS_ORIGINS` | `""` | `http://localhost:5173` |
- Coacción: si `DEBUG is True` y `APP_ENV == "production"`, se fuerza `APP_ENV="development"`.
- Los overrides explícitos por constructor/env siempre ganan (solo se derivan campos que quedaron en `None`).
- `validar_postura_seguridad` se mantiene (keyeado sobre `DEBUG` ya derivado).
- `run.sh --debug` exporta `APP_ENV=development`; `.env.example` documenta `APP_ENV=production`.

## 5. Matriz de Pruebas (RED Suite)

| # | Escenario | Assert |
|---|---|---|
| P1 | `DEBUG=True` sin `APP_ENV` | `APP_ENV == "development"` y `DEBUG is True` (coacción, sin error) |
| P1b | sin argumentos (o `APP_ENV=production`) con secreto fuerte | `APP_ENV == "production"`, `DEBUG is False` |
| P2 | `APP_ENV=development` | defaults dev: console, DEBUG, docs on, CORS localhost |
| P3 | `APP_ENV=production` con secreto débil | `ValidationError` |
| P4 | `APP_ENV=production` con secreto fuerte | defaults prod: json, INFO, docs off, CORS vacío |
| P5 | override explícito (`LOG_FORMAT=json` en dev) | gana el override |
| P6 | arquitectura (regresión) | `domain/` y `application/` no importan `infrastructure` |

## 6. Criterios del Gauntlet

`venv/bin/pytest`, `venv/bin/ruff check .`, `venv/bin/ruff format --check .`, `venv/bin/pyright src/`, `venv/bin/python scripts/verify_architecture.py`. Reglas inmutables: imports absolutos `from src...`, `__init__.py` de 0 bytes, prohibidos `# type: ignore`/`# noqa`/`cast(Any, ...)`/`@pytest.mark.skip`.
