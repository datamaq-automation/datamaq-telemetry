# Spec: Refactor DDD de Nomenclatura — `datamaq-telemetry`

**Sesión Hija:** Copiar como `datamaq-telemetry/specs/ddd-naming-refactor.md`

> **Estado:** ❌ revertida (2026-10-04, commit `1fba1dd`) · **Fecha:** 2026-10-04 · **Dueño:** Agustín\
> **Decisión padre:** `decisions/2026-10-04_ddd-naming-telemetry.md` (D1 ✅ Sí, D2 ❌ No, D3 ✅ Sí): D1 y D3 quedan sin efecto, ver "Revisión"\
> **Estimado:** 1–2 horas TDD + refactor

---

## Revisión 2026-10-04: rename revertido

**Qué pasó.** El rename `Carga` → `Máquina` (commits `a799055`..`8325519`) chocó con un concepto que ya
existía en otro bounded context: `Maquina` de **disponibilidad/OEE** (`src/domain/disponibilidad/`),
una máquina con medidor propio cuya marcha/parada se infiere con `umbral_marcha_w` y
`ventana_persistencia_*`. Los DTOs y el mapper de `Carga` se escribieron encima de `maquina_dto.py` y
`maquina_mapper.py` y borraron los de disponibilidad. Resultado: 48 errores de pyright y CI rojo desde
`61e1213`. Completar el rename como proponía el plan de seguimiento (`MaquinaCreateDTO` →
`MáquinaCreateDTO`) habría conectado los endpoints `/disponibilidad/maquinas` al DTO de NILM sin dar
ningún error de tipos.

**Decisión del dueño.** La entidad de desagregación vuelve a llamarse `Carga`:

- "Carga" es el término IEC 60050 para un receptor que absorbe potencia de la red (una heladera, un
  circuito de iluminación, un motor). Es exactamente lo que el NILM infiere sobre un medidor agregado.
  Una máquina es solo un caso posible.
- `Maquina` queda para disponibilidad/OEE, donde **sí** es una máquina con medidor dedicado. Son dos
  conceptos distintos y conviene que tengan dos nombres distintos.
- Identificadores en ASCII (convención del repo: `Campana`, no `Campaña`). Que dos clases se
  distingan solo por una tilde (`Maquina` vs `Máquina`) es una trampa.

**Qué se conserva.** El rename `Campana` → `Ensayo` de caracterización (nomenclatura interna, sin
tocar rutas ni campos JSON) se hace en un commit aparte.

**Pendiente en el repo padre.** Registrar una decisión que reemplace D1/D3 de
`decisions/2026-10-04_ddd-naming-telemetry.md` y actualizar `TODO.md`.

---

## 1. Objetivo y Contexto (COMPLETADO POR PADRE)

### Objetivo

Renombrar entidades y servicios del dominio (`Carga` → `Máquina`, `CargaCandidata` → `MáquinaInferida`) y renombrar directorio (`cargas/` → `maquinas/`) para alinear nomenclatura con el **Ubiquitous Language del dominio industrial**, mejorando legibilidad y mantenibilidad **sin cambios a contratos de API pública**.

### Alcance

- **Entidades dominio:** `Carga` → `Máquina`
- **Servicios:** `ClasificadorCargasReglasService` → `ClasificadorMáquinasReglasService`
- **DTOs:** `CargaCandidataResponseDTO` → `MáquinaInferidaDTO`
- **Puertos:** `RepositorioCargasPort` → `RepositorioMáquinasPort`
- **Infraestructura:** renombrar archivos y directorios (`cargas_router.py` → `maquinas_router.py`, etc.)
- **Tests:** \~40 tests unitarios/integración ajustados
- **Directorio:** `src/domain/cargas/` → `src/domain/maquinas/`

### Fuera de alcance

**NO incluir en Fase 1 (decidido por dueño, D2 ❌):**

- Expansión de acrónimos (SEC, EnPI, P/Q/S, etc.) → Fase 2, sesión futura
- Cambios a DTOs públicos que afecten API contracts

### Archivos afectados (certezas verificadas)

**Dominio:**

```
src/domain/cargas/                         → renombrar a src/domain/maquinas/
  ├── entities.py                           (Carga → Máquina, CargaCandidata → MáquinaInferida)
  ├── repository.py                         (RepositorioCargasPort → RepositorioMáquinasPort)
  └── service.py (si existe)                (ClasificadorCargasReglasService → ClasificadorMáquinasReglasService)
```

**Aplicación:**

```
src/application/dtos/sge_dto.py            (CargaCandidataResponseDTO → MáquinaInferidaDTO, y otros)
src/application/mappers/                   (actualizar mapeos de Máquina → DTO)
src/application/use_cases/                 (actualizar inyecciones de RepositorioMáquinasPort)
```

**Infraestructura:**

```
src/infrastructure/persistence/
  └── cargas_repository.py                 → maquinas_repository.py (implementación RepositorioMáquinasPort)
src/infrastructure/routers/
  └── cargas_router.py                     → maquinas_router.py (endpoints de máquinas)
src/infrastructure/
  └── dependencies.py                      (inyecciones: actualizar imports)
```

**Tests (\~40 tests):**

```
tests/unit/domain/cargas/                  → tests/unit/domain/maquinas/ (renombrar + ajustar imports)
tests/integration/cargas_router/           → tests/integration/maquinas_router/ (renombrar + ajustar imports)
tests/unit/application/dtos/               (ajustar DTO tests)
```

**Servidor:**

```
src/server.py                              (agregar router de maquinas, remover cargas)
src/application/dependencies.py            (inyección del puerto)
```

### Bloqueadores

**Ninguno.** Fase 1 es autocontenida, bajo riesgo.

---

## 2. Dominio & Puertos

> Sesión hija: completa esta sección

- [ ] Entidad `Máquina` en `src/domain/maquinas/entities.py`
  - Renombrar `Carga` → `Máquina`
  - Renombrar `CargaCandidata` → `MáquinaInferida`
  - Mantener atributos y lógica igual
  - Tests unitarios ajustados para nueva nomenclatura
- [ ] Puerto `RepositorioMáquinasPort` en `src/domain/maquinas/repository.py`
  - Renombrar `RepositorioCargasPort` → `RepositorioMáquinasPort`
  - Métodos: `crear_carga` → `crear_maquina`, etc. (según naming de métodos actual)
- [ ] Servicio `ClasificadorMáquinasReglasService` en `src/domain/maquinas/service.py` (o donde viva)
  - Renombrar si existe `ClasificadorCargasReglasService`
- [ ] Validar: `domain/maquinas/` sin dependencias externas (stdlib-only)

---

## 3. Casos de Uso & DTOs

> Sesión hija: completa esta sección

- [ ] DTO `MáquinaInferidaDTO` en `src/application/dtos/sge_dto.py`
  - Renombrar `CargaCandidataResponseDTO` → `MáquinaInferidaDTO`
  - Campos: sin cambios funcionales
  - Tests de DTO ajustados
- [ ] Otros DTOs con "Carga" en el nombre (búsqueda grep)
  - Renombrar `Carga*DTO` → `Máquina*DTO` según patron
- [ ] Maperos en `src/application/mappers/`
  - Renombrar métodos: `carga_a_dto` → `maquina_a_dto`, etc.
  - Actualizar imports
- [ ] Use cases que inyecten `RepositorioMáquinasPort`
  - Actualizar inyecciones de dependencias
  - Nombres de parámetros: `cargas_repo` → `maquinas_repo`, etc.
- [ ] Tests de aplicación (\~13 tests): ajustar assertions y setup

---

## 4. Matriz de Pruebas (RED Suite)

> Sesión hija: documenta los tests que pasarán

- **Unit:** Dominio (entidad, reglas de clasificación), DTOs, maperos
  - \~12 tests de dominio (cargas/ → maquinas/)
  - \~13 tests de aplicación (DTOs, maperos)
  - Tests de mapeo de Máquina → DTO
- **Integration:** Router de máquinas, endpoints (si hay)
  - \~15 tests de router (cargas_router/ → maquinas_router/)
  - Verificar que endpoints HTTP respondan igual (contrato sin cambios)
- **Arquitectura:**
  - `scripts/verify_architecture.py` debe pasar (domain/ stdlib-only)
  - Tamaño: ningún archivo >500 líneas
- **Full Gauntlet:**
  - `pytest` (1600+ tests): todos verdes
  - `pyright`: 0 errores
  - `ruff`: 0 violations
  - Migración Alembic (si aplica): ninguna requerida (cambio puro de código, sin DB)

---

## 5. Desglose de Commits Atómicos Planificados

> Sesión hija: ejecuta en este orden, TDD (RED → GREEN)

### Commit 1: Dominio — Renombrar Máquina + tests

```
chore(domain): renombrar Carga → Máquina en src/domain/

Cambios:
- Renombrar directorio: src/domain/cargas/ → src/domain/maquinas/
- Entidad: Carga → Máquina
- Entidad: CargaCandidata → MáquinaInferida
- Puerto: RepositorioCargasPort → RepositorioMáquinasPort
- Servicio: ClasificadorCargasReglasService → ClasificadorMáquinasReglasService
- Tests: ajustar 12 tests unitarios de dominio
- Validar: domain/maquinas/ sin deps externas
```

**Checks:**

- `pytest tests/unit/domain/maquinas/` verde
- `pyright` limpio
- Arquitectura OK

### Commit 2: Aplicación — DTOs + Maperos

```
chore(application): renombrar DTOs y maperos (Carga → Máquina)

Cambios:
- DTO: CargaCandidataResponseDTO → MáquinaInferidaDTO
- Otros DTOs con "Carga" renombrados
- Maperos: actualizar nombres de funciones
- Tests: ajustar 13 tests de aplicación
- Imports: actualizar en secciones 2–5 (aplicación)
```

**Checks:**

- `pytest tests/unit/application/` verde
- `pyright` limpio
- Mapeos correctos

### Commit 3: Infraestructura — Router + Repository

```
chore(infrastructure): renombrar router y repository (cargas → maquinas)

Cambios:
- Router: src/infrastructure/routers/cargas_router.py → maquinas_router.py
- Repository: src/infrastructure/persistence/cargas_repository.py → maquinas_repository.py
- server.py: agregar route(maquinas_router), remover cargas_router
- dependencies.py: actualizar inyecciones
- Tests: ajustar ~15 tests de integración (router)
```

**Checks:**

- `pytest tests/integration/maquinas_router/` verde
- `pyright` limpio
- Endpoints HTTP responden igual (sin cambios de API)

### Commit 4 (opcional): Limpieza de imports globales

```
chore(all): actualizar imports de maquinas en todo el codebase

Si hay imports no capturados en commits 1–3:
- src/application/dependencies.py
- src/server.py (si no fue actualizado en commit 3)
- Tests globales
```

---

## 6. Criterios del Gauntlet

> Sesión hija: verifica todos estos antes de commit final

- [ ] `pytest` (1600+ unit + integration tests)
  - Salida esperada: `X passed` (X ≈ 1600)
  - Ningún test `FAILED` o `ERROR`
- [ ] `pyright`
  - Salida esperada: `0 errors, 0 warnings`
- [ ] `ruff check .`
  - Salida esperada: 0 violations
- [ ] `scripts/verify_architecture.py`
  - `domain/` solo stdlib: ✓
  - Sin ciclos: ✓
- [ ] Tamaño de archivos
  - Ninguno >500 líneas: ✓
- [ ] Migración Alembic (si aplica)
  - No requerida (cambio de código puro)
- [ ] Spec completada
  - Secciones 1–6 cerradas
  - Estado: "aprobada · bloque cerrado: sí"

---

## Instrucciones para la sesión hija

1. **Copia este bloque** como `datamaq-telemetry/specs/ddd-naming-refactor.md`
2. **Mantén sección 1** exacta (contexto del padre, no editar)
3. **Completa secciones 2–6** según tu `AGENTS.md`:
   - Sección 2: detalle de dominio (entidades, puertos, tests)
   - Sección 3: detalle de DTOs y maperos
   - Sección 4: matriz de pruebas (qué tests pasan en cada etapa)
   - Sección 5: commits atómicos (orden, contenido exacto)
   - Sección 6: checks de gauntlet (qué comandos correr, salida esperada)
4. **Ejecuta TDD:**
   - RED: escribe test fallido
   - GREEN: renombra (refactor + imports)
   - REFACTOR: limpia imports no usados (hook de editor)
5. **Commit al cierre de cada sección** (atómicos, secciones 5)
6. **Pre-push:** Gauntlet completo (`scripts/pre-push.sh` corre todo)
7. **Push:** Cuando todos los checks estén verdes

---

## Quick Reference: Comandos

```bash
# Dentro de datamaq-telemetry, con .venv/ Python 3.12

# Correr tests de dominio
.venv/bin/python -m pytest tests/unit/domain/maquinas/ -v

# Correr tests de integración
.venv/bin/python -m pytest tests/integration/maquinas_router/ -v

# Gauntlet completo
.venv/bin/python -m pytest tests/ -v  # todos
.venv/bin/python -m pyright src/
.venv/bin/python -m ruff check .
python scripts/verify_architecture.py

# O simplemente correr el hook de pre-push
bash scripts/pre-push.sh
```

---

## Notas de proceso

- **Directorio:** cambio de `cargas/` a `maquinas/` es junto con renombrado de entidades (D3 ✅ aprobado)
- **Sin acrónimos:** D2 rechazado, Fase 2 separada (SEC, EnPI, etc.)
- **API pública:** sin cambios (DTOs internos, serialización igual)
- **Padre:** verificará cruzada al cierre (entidad `Máquina` en código, DTOs renombrados, gauntlet verde, spec completa)

---

## Checklist de inicio (sesión hija)

- [ ] Copia este doc como `specs/ddd-naming-refactor.md` en tu repo
- [ ] Lee `decisions/2026-10-04_ddd-naming-telemetry.md` (contexto de decisiones)
- [ ] Verifica que `src/domain/cargas/` existe (antes de renombrar)
- [ ] Ejecuta `pytest --collect-only` para contar tests actuales
- [ ] Crea rama de trabajo (sugerencia: `feat/ddd-naming-maquina`)
- [ ] **Comienza Commit 1 (TDD)**
