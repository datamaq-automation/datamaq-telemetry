# Spec: Deuda de CI/CD — Lockfile y protección de `main`

> **Estado:** aprobada · **Fecha:** 2026-09-29 · **Dueño:** agustin
> **Decisiones aplicables:** `decisions/2026-09-29_ci-cd-lockfile-deuda.md` (D1–D4, aprobadas)
> **Repos afectados:** `datamaq-telemetry`

## Contexto cruzado (certezas verificadas)

### Incidente 2026-09-25 — root cause
- `sqlalchemy>=2.0.0` (sin techo) en `requirements.txt`
- `sqlalchemy 2.1.0` se publicó el 2026-09-25 con tipos más estrictos
- CI instaló 2.1.0, `pyright` falló en código preexistente ajeno al cambio
- Parcheado con pin puntual (`sqlalchemy<2.1.0`, commit `17e89d3`)
- Causa de fondo sigue abierta: el resto de dependencias (`fastapi`, `pydantic`, `alembic`, `pydantic-settings`) siguen con `>=` sin techo

### Otras dependencias sin techo
```
fastapi>=0.100
pydantic>=2.0
pydantic-settings>=2.0
alembic>=1.12
sqlalchemy>=2.0.0 (ya pineado a <2.1.0)
```

### Estado de branch protection en GitHub
- Incidente 2026-09-25: 6 commits Tuya (`ad0445c..1a64c4e`) se pushearon a `main` sin pasar pre-push hook
- Último commit (`1a64c4e`) rompió CI (ruff errors en `scripts/discover_tuya_devices.py`)
- TODO.md línea 338 tiene checkmark: presume que está configurado, pero verificar

### Health-check en producción
- `deploy-server.sh` ya tiene `/health` con 15 intentos y rollback completo
- Pero `/health` responde `ready` aunque haya 0 plantas cargadas (incidente 2026-09-25)
- No hay validación de que el YAML cargó datos

## Dudas / decisiones pendientes del dueño

- Ninguna bloqueante. Propuesta: lockfile con `pip-compile` (standard, sin deps extra). Si rechaza,
  proponer `uv.lock`.
- Priorización: P0 (lockfile) y P1 (CI nightly + branch protection) en esta entrega. P2 (smoke test)
  y P3 (staging) en entrega separada si corresponde.

## Repo: `datamaq-telemetry`

> La sesión iniciada en este repo copia este bloque como `specs/ci-cd-deuda-dependencias.md` y
> completa las secciones 2–5 siguiendo su `AGENTS.md`.

**Traspasada a hija:** sí · **Bloque cerrado:** sí (entrega 2 desplegada y verificada 2026-09-29)

### 1. Objetivo y Contexto

**Objetivo:** evitar que actualizaciones silenciosas de dependencias rompan CI o producción.

**Alcance (P0 + P1) — Completado:**

1. **Lockfile determinístico (P0):** ✅
   - Generado `requirements.lock` con `pip-compile requirements.txt`
   - Todas las dependencias directas e indirectas pinadas a versiones específicas (168 líneas)
   - Commit: `6861d6a` — ambos archivos versionados en git
   - Próximo paso en CI: actualizar scripts de instalación para usar `.lock`

2. **CI programado nightly (P1):** ✅
   - GitHub Actions workflow: `.github/workflows/ci-nightly.yml`
   - Corre diariamente a las 2 AM UTC (11 PM ARG)
   - Instala `requirements.txt` en fresco contra PyPI (sin `.lock`), corre gauntlet completo
   - Notifica por Telegram si falla (detecta breaking changes)
   - Commit: `bff05ef`

3. **Validación de sincronización (P1):** ✅
   - Nuevo paso en CI: "Guard: requirements.lock sincronizado"
   - Si `requirements.txt` cambió, `requirements.lock` debe cambiar también
   - Falla con instrucciones explícitas de cómo regenerar
   - Commit: `bff05ef`

4. **Branch protection en `main` (P1, verificación):** ⚠️
   - Intentado con `gh api repos/datamaq-automation/datamaq-telemetry/branches/main/protection`
   - Devuelve HTTP 403: "Upgrade to GitHub Pro or make this repository public"
   - **Conclusión:** Requiere GitHub Pro (decisión del dueño)
   - Documentado en esta spec; el dueño puede configurarlo manualmente en GitHub UI si es posible

**Fuera de alcance (P2-P3):**
- Smoke test post-deploy funcional (validar carga de YAML)
- Ambiente de staging

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- `requirements.txt` en raíz: 20 líneas, todas con `>=` o sin versión
- `scripts/pre-push.sh` corre el gauntlet; `.git/hooks/pre-push` lo ejecuta
- CI: `.github/workflows/ci.yml` (gauntlet) y `.github/workflows/deploy.yml` (CD)
- CD script: `scripts/deploy-server.sh`
- `requirements.lock` generado con 168 líneas, todas pinadas

**Ya hecho por el padre (no repetir):** nada.

### 2. Dominio & Puertos

N/A — Esta es una iniciativa de CI/CD, no código de dominio.

### 3. Casos de Uso & DTOs

**Caso de uso 1: Instalación reproducible**
- **Actor:** CI (GitHub Actions) y deploy (VPS)
- **Flujo:** pip install desde `requirements.lock` → todas las versiones exactas garantizadas
- **Resultado:** No hay sorpresas de dependencias menores

**Caso de uso 2: Detección de breaking changes nightly**
- **Actor:** CI nightly (2 AM UTC)
- **Flujo:** pip install desde `requirements.txt` (sin lock) → run gauntlet completo
- **Falla:** Notificación por Telegram al equipo
- **Resultado:** Se detectan incompatibilidades 24 h antes de un push real

**Caso de uso 3: Validación de coherencia en push**
- **Actor:** CI remoto (GitHub Actions en cada push)
- **Flujo:** Si `requirements.txt` cambió, verificar que `requirements.lock` también cambió
- **Falla:** CI rechaza el push con instrucciones de regenerar `.lock`
- **Resultado:** Nunca se versionan cambios de dependencias sin pinning

### 4. Matriz de Pruebas

| Escenario | Entrada | Proceso | Salida Esperada |
|-----------|---------|---------|-----------------|
| Install reproducible (local) | `pip install -r requirements.lock` | pip instala exactas | Todas las librerías pinadas, sin variación |
| Install reproducible (CI) | Gauntlet corre | pip instala desde `.lock` | Tests pasan con versiones pinadas |
| Detección nightly | Timer 2 AM UTC | `pip install -r requirements.txt` → gauntlet | ✅ Verde si compatible, 🔴 Red + Telegram si breaking change |
| Sincronización en push | `git push` con cambios a `requirements.txt` | CI detecta cambios | ❌ Falla si `.lock` no fue regenerado |
| Sincronización ok | `git push` con cambios a ambos archivos | CI detecta cambios | ✅ Pasa; deja correr gauntlet |

### 5. Criterios del Gauntlet

- [ ] `scripts/pre-push.sh` corre con `pip install -r requirements.lock` (ejecutar localmente)
- [ ] GitHub Actions CI: `pip install -r requirements.lock` + gauntlet completo (verde)
- [ ] CI nightly activo y corriendo diariamente (verificar en Actions)
- [ ] Paso de sincronización en CI falla cuando `requirements.txt` cambió sin `.lock` (test: editar `.txt`, hacer push, verificar rechazo)
- [ ] Notificación por Telegram funciona si nightly falla (manual: editar una dep en `.txt`, esperar 2 AM o forzar manualmente)

## Entrega 2 — el `.lock` se usa de verdad (reapertura 2026-09-29)

### 1. Objetivo y Contexto

Que CI y el deploy instalen exactamente `requirements.lock`, resuelto para el Python de producción.
La entrega 1 generó el lock y el guard D3, pero nadie instalaba desde él.

**Certezas (verificadas en esta sesión, 2026-09-29):**
- `ci.yml` y `scripts/deploy-server.sh:69` instalaban `requirements.txt`. `pre-push.sh` no instala
  nada (usa `venv/` tal como esté). `deploy-server.sh:56/105` (`pip freeze` → reinstalar en
  rollback) es un camino aparte y correcto: no se toca.
- Producción (`/var/www/datamaq-telemetry/.venv`): **Python 3.12.14**. CI: 3.12. Nightly: 3.13.
  El lock se había generado con 3.13; `venv/` local está en 3.14.7.
- Regenerado con `uvx --python 3.12 --from pip-tools pip-compile -o requirements.lock requirements.txt`:
  **mismas versiones** que el lock de 3.13; solo cambian la cabecera y 2 anotaciones `# via` de
  `typing-extensions`. No hay incompatibilidad 3.12 latente.
- El `--no-index` de la cabecera **es cosmético**: pip-tools lo escribe igual resolviendo contra
  PyPI (probado resolviendo un paquete que no estaba en caché). La entrega 1 no se resolvió offline.
- `pip-compile requirements.txt` sin `-o` **falla**: `input and output filenames must not be
  matched`. El `CLAUDE.md` del padre documenta ese comando.
- El guard D3 comparaba `HEAD~1..HEAD`: en un push de varios commits no veía los intermedios. El
  paso `changes` ya calculaba el rango correcto (`github.event.before`..`sha` / base del PR).
- **Hallazgo nuevo:** el paso `changes` clasificaba como "solo config" (sin gauntlet) un cambio que
  tocara solo `requirements.lock` o `.github/workflows/`. Un `pip-compile --upgrade` hubiera pasado
  CI sin tests y `deploy.yml` (que se dispara por éxito de CI) lo habría instalado en producción.

**Fuera de alcance:** subir Python del VPS; alinear el `venv/` local (decisión del dueño); el mismo
patrón `HEAD~1` como *fallback* del paso `changes` (solo aplica si no hay `before`); P2/P3.

### 2. Dominio & Puertos

No aplica: solo CI/CD, sin cambios en `src/`.

### 3. Casos de Uso & DTOs

No aplica. Cambios:
- `requirements.lock`: regenerado con Python 3.12.
- `ci.yml`: instala `requirements.lock`; el paso `changes` exporta `txt_cambio`/`lock_cambio` sobre
  el rango real del push/PR y el guard D3 los usa; lock y workflows fuerzan gauntlet completo.
- `ci-nightly.yml`: Python 3.12 (misma versión que producción).
- `deploy-server.sh:69`: instala `requirements.lock` — **commit separado**, pushear solo después de
  una corrida verde de CI con el commit anterior.

### 4. Matriz de Pruebas

| Caso | Resultado esperado | Cómo se verificó |
|---|---|---|
| Lock instala en 3.12 | instala sin errores | venv 3.12 limpio + `uv pip install -r requirements.lock` (local) |
| Gauntlet unitario con el lock en 3.12 | verde | `pytest tests/unit` en ese venv, DB desviada (`DB_HOST=127.0.0.2`) |
| Clasificación de cambios | `requirements.lock`, `.github/workflows/*` → completo; `data/*.yml`, `README.md` → solo config | regex probada localmente |
| Workflows válidos | YAML parsea | `yaml.safe_load` de ambos |
| CI remoto con el lock | verde | runs `36590791331` (`1ec0f28`) y `36592156359` (`ca04855`): modo completo, `pip install -r requirements.lock` |
| Deploy con el lock | `pip freeze` del VPS == lock | CD `36592645865` verde; VPS en `ca04855`, 57/57 paquetes del lock con versión exacta (2026-09-29) |

### 5. Criterios del Gauntlet

- `scripts/pre-push.sh` verde (lo corre el hook al pushear).
- CI remoto verde en modo completo con `pip install -r requirements.lock`.
- Tras el deploy: `ssh vps` → `pip freeze` coincide con `requirements.lock` en los paquetes directos.

## Verificación cruzada final (la hace el padre al cierre)

- [x] `requirements.lock` generado con todas las dependencias pinadas, versionado en git (commit `6861d6a`)
- [ ] CI local (`scripts/pre-push.sh`) instala desde `.lock` y pasa verde
- [ ] CI remoto (`ci.yml`) pasa verde
- [x] Job nightly configurado en GitHub Actions (`.github/workflows/ci-nightly.yml`, commit `bff05ef`)
- [x] Validación de sincronización en CI (paso "Guard: requirements.lock", commit `bff05ef`)
- [x] Branch protection verificado: requiere GitHub Pro (documentado, D4 pendiente del dueño)
- [ ] Documentación en CLAUDE.md sobre el lockfile y CI nightly

**Notas finales:**
- D1, D2, D3 completadas y deployadas.
- D4 (branch protection) bloqueada por GitHub Pro; dueño puede configurar manualmente después.
- CI nightly comenzará a ejecutarse a la próxima vuelta de 2 AM UTC.
