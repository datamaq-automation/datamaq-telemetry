# Slug legible de Planta (`GET /api/v1/plantas`)

> **Estado:** implementado · **Fecha:** 2026-09-25
> **Decisión aplicable:** `../decisions/2026-09-25_slugs-legibles-url-planta-dispositivo.md` (repo padre)
> **Spec cruzada:** `../specs/slugs-legibles-en-url.md` (repo padre) → bloque `## Repo: datamaq-telemetry`

## 1. Objetivo y Contexto

**Objetivo:** exponer un identificador corto y legible (slug) para planta en el DTO de catálogo, sin
reemplazar el UUID interno (PK real, sigue siendo el id que usa el resto del backend puertas
adentro).

**Alcance:** campo `slug` en `Planta` (dominio) y `PlantaResponseDTO`/`PlantaBaseDTO`, único por
organización, fijo al declararse.

**Fuera de alcance:** dispositivo (decisión del padre lo excluye explícitamente: truncar el UUID no
garantiza unicidad); cambiar la PK real de planta; migrar/renombrar UUIDs existentes; el consumo del
slug en rutas de la SPA (bloque `app-datamaq`, repo separado).

**Certeza verificada al arrancar este bloque (no estaba en la spec del padre):** `Planta` **no tiene
tabla en MySQL** — es dato maestro declarado en `data/organizaciones.yml`
(`src/infrastructure/yaml/repositories/organizaciones_repository.py:196-230`), igual que
`Organizacion`. No existe migración de planta ni constraint de DB posible para la unicidad del slug;
el patrón real de esta base para invariantes de datos maestro del YAML es un verificador que corre en
el arranque, advierte y no bloquea (`src/infrastructure/yaml/verificador_unifilar.py`,
`verificador_facturas.py`, orquestados desde
`src/infrastructure/fastapi/startup_verificaciones.py`). Este bloque sigue ese patrón en vez del
"constraint de DB" que menciona la decisión del padre, porque tal constraint no tiene dónde vivir.

## 2. Dominio & Puertos

- `Planta` (`src/domain/telemetria/entities.py`) gana el campo `slug: str = ""` y un
  `__post_init__` que, si no viene declarado, lo deriva de `nombre` con
  `generar_slug_planta()` (mismo módulo, dominio puro — solo `re`/`unicodedata` de stdlib, respeta
  la regla de capas de `scripts/verify_architecture.py`).
- `generar_slug_planta(nombre)`: normaliza acentos (NFKD → ASCII), minúsculas, espacios → `-`,
  descarta todo lo que no sea `[a-z0-9-]`, colapsa guiones repetidos y recorta los de punta.
  Ej.: `"Planta San Martín (Sur)"` → `"planta-san-martin-sur"`.
- **Fijo al crearse:** si el YAML declara `plantas[].slug` explícitamente, ese valor gobierna y no se
  recalcula aunque `nombre` cambie después (`__post_init__` solo deriva cuando `slug` viene vacío) —
  mismo criterio "lo declarado gobierna" que ya usa este archivo para `medidores`/`nodos_unifilar`
  (comentario en `data/organizaciones.yml:8-16`). Hoy ninguna planta declara `slug`; las 4 existentes
  se derivan del nombre sin colisión (verificado con el repositorio real, ver §4).
- `YamlOrganizacionesRepository.obtener_planta_por_id`/`listar_plantas` pasan `p.get("slug")` al
  construir la entidad (o `""` si no está, activando la derivación).
- Puerto sin cambios (`RepositorioOrganizacionesPort` ya devuelve `Planta`).

## 3. Casos de Uso & DTOs

- `PlantaBaseDTO`/`PlantaResponseDTO` (`src/application/dtos/organizacion_dto.py`) ganan `slug: str`
  (obligatorio en el DTO: la entidad garantiza que nunca llega vacío al mapper).
- `OrganizacionMapper.planta_to_dto` (`src/application/mappers/dispositivo_mapper.py`) copia
  `entity.slug`.
- `GestionarDispositivosUseCase.listar_plantas` sin cambios (ya delega en el mapper); expone `slug`
  en cada elemento de `GET /api/v1/plantas` sin tocar el router.

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_slug_planta.py` (nuevo):
- `generar_slug_planta`: minúsculas + espacios (`"Planta Principal UPP"` → `"planta-principal-upp"`),
  acentos y caracteres no alfanuméricos (`"Planta San Martín (Sur)"` →
  `"planta-san-martin-sur"`), guiones repetidos/espacios de punta colapsados.
- `Planta`: deriva el slug del nombre si no se declara; respeta el slug declarado aunque no coincida
  con el nombre (prueba explícita de "fijo al crearse").
- `verificar_slugs_planta` (nuevo, `src/infrastructure/yaml/verificador_slugs_planta.py`): sin
  colisiones → `{"colisiones": 0}`; dos plantas de la misma organización con el mismo slug derivado →
  1 colisión reportada; mismo slug en organizaciones **distintas** → 0 colisiones (unicidad es por
  organización, no global); y una corrida contra el `data/organizaciones.yml` real, que hoy da
  0 colisiones.

`tests/unit/test_organizaciones_router.py` (existente, extendido): `test_listar_plantas_superadmin`
ahora afirma que `slug` viaja en cada elemento de la respuesta de `GET /api/v1/plantas`.

## 5. Criterios del Gauntlet

- `venv/bin/python -m pytest -q` completo (no solo el archivo nuevo) en verde: **1604 passed**,
  corrido también con `DB_HOST=127.0.0.2 DB_PORT=1` (como CI, sin tocar la DB real).
- `venv/bin/python -m pyright`: **0 errors, 0 warnings**.
- `venv/bin/python scripts/verify_architecture.py`: **PASS** (el nuevo código de `entities.py` sigue
  usando solo stdlib en `domain/`).
- No se tocó ninguna migración: no aplica `tests/unit/test_migraciones.py`.
