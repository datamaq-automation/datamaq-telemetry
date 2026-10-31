# Spec: Tarifas y parámetros regulatorios en SQL (fase 1)

> Copia del bloque de telemetry del spec del repo padre (sección 1 escrita por el padre, verificada en cc34c26). Las secciones 2 a 6 las completa la sesión hija.
> Issue: datamaq-automation/datamaq#111 · Decisión: decisions/2026-10-31_tarifas-y-parametros-regulatorios-en-sql.md (repo padre)

## Repo: `datamaq-telemetry`

> La sesión iniciada en este repo copia este bloque como `specs/tarifas-en-sql.md` del repo y completa las secciones **2. Dominio & Puertos**, **3. Casos de Uso & DTOs**, **4. Matriz de Pruebas (RED Suite)**, **5. Desglose de Commits Atómicos Planificados** y **6. Criterios del Gauntlet** siguiendo su `AGENTS.md`. El padre escribe **solo** la sección 1.

**Traspasada a hija:** no · **Bloque cerrado:** no

### 1. Objetivo y Contexto

**Objetivo:** que ningún precio, parámetro regulatorio ni factura verificada viva como literal en `domain` ni en `application`. Pasan a tablas SQL versionadas por vigencia, con distribuidora, tarifa y fuente (documento y método de carga). Esto cierra la infracción R2 de la auditoría del SRS (Regla 4, parámetros críticos fuera del código).

**Alcance:**
- Tablas con vigencia desde/hasta, distribuidora, tarifa, `fuente_archivo` y método de carga, para: (a) el precio de capacidad por período; (b) los períodos con factura verificada; (c) los parámetros regulatorios (factor de recargo por exceso, límite de tg φ del régimen de 1992, umbral de FP por distribuidora y tarifa).
- Puerto en `domain` (solo stdlib) para consultar esos datos, adaptador SQLAlchemy en `infrastructure`, y cableado por inyección (`Depends`) sin tocar `routes/` con ORM (el gate de controladores delgados está activo desde #121).
- Migración Alembic que crea las tablas y carga las filas de hoy, con su fuente, **idénticas** a los literales actuales.
- Los 0,95 de FP se leen del repositorio por distribuidora y tarifa. La carga inicial conserva el valor 0,95 donde hoy se usa, para no cambiar el comportamiento. No se decide aquí qué valor corresponde a cada distribuidora: esa es la fase 2 y requiere verificar el régimen de EDELAP (OCEBA).

**Fuera de alcance:**
- Cambiar cualquier valor de facturación. Ninguno cambia sin decisión del dueño.
- El modelo `esquema_potencia` y la fórmula de costo de `consultar_costo_estimado.py:139-142` (M-1/M-2, fase 2).
- Migrar `data/facturas_distribuidora.yml` ni tocar `datamaq-data`.
- Cambios de contrato en la API ni en `app-datamaq`.
- Aplicar la migración en producción. Eso es parte del release de telemetry y lo autoriza el dueño.

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- Los literales listados arriba son todo lo que hay; se borran de `domain` al terminar. Las funciones puras de cálculo (`calcular_recargo_exceso_potencia`, `calcular_penalizacion_reactiva_edelap`) se quedan en dominio y reciben los datos por parámetro.
- `obtener_tarifa_capacidad(distribuidora, periodo)` y `_factura_verificada(planta_id, periodo)` hoy consultan una tupla en memoria; son el punto de reemplazo por el puerto.
- El dominio solo admite stdlib (`tests/test_architecture.py`): ni SQLAlchemy ni Pydantic en el puerto.
- Los tests de `tests/unit/` citados fijan los importes de hoy (por ejemplo, recargo de Edesur 2025-07). Deben seguir verdes con las mismas expectativas; si hay que cambiar una expectativa, se reporta al padre antes de seguir.
- Para que los tests de dominio y de aplicación no dependan de la base, se agrega un repositorio en memoria del puerto, con las mismas filas iniciales.

**Ya hecho por el padre (no repetir):** la decisión (`decisions/2026-10-31_tarifas-y-parametros-regulatorios-en-sql.md`), el Issue #111 y esta sección. La auditoría que originó el hallazgo está en `auditorias/2026-10-31_telemetry-vs-srs-backend.md`.

<!-- Secciones a completar por la sesión hija al adoptar el bloque:
### 2. Dominio & Puertos
### 3. Casos de Uso & DTOs
### 4. Matriz de Pruebas (RED Suite)
### 5. Desglose de Commits Atómicos Planificados
### 6. Criterios del Gauntlet
-->


### 2. Dominio & Puertos

- **Puerto (`src/domain/telemetria/parametros_regulatorios.py`, solo stdlib):** `RepositorioParametrosRegulatoriosPort` con `obtener_tarifa_capacidad(distribuidora, periodo)`, `obtener_factura_verificada(planta_id, periodo)`, `factor_recargo_exceso()` y `limite_tg_fi_regimen_1992()`. Los tipos de `TarifaCapacidad` y `FacturaVerificada` van por `TYPE_CHECKING` para no crear ciclos en runtime.
- **Funciones puras (se quedan en dominio, reciben datos por parámetro):**
  - `obtener_tarifa_capacidad(repo, distribuidora, periodo)`: delega en el puerto.
  - `calcular_recargo_exceso_potencia(csc_kw, adquirida_kw, tarifa, factor_recargo)`.
  - `calcular_penalizacion_reactiva_edelap(periodo, fuente_archivo, tg_fi_por_bloque, limite_tg_fi)`.
  - `calcular_penalizacion_periodo(repo, planta_id, periodo)`.
- **Literales eliminados de `domain`:** `_TARIFAS_CAPACIDAD`, `FACTOR_RECARGO_EXCESO`, `LIMITE_TG_FI_REGIMEN_1992` y `_FACTURAS_VERIFICADAS`.
- **Repositorio en memoria (`src/adapters/gateways/in_memory_parametros_regulatorios.py`):** misma carga inicial que la migración, para tests de dominio y aplicación.
- **Adaptador SQLAlchemy (`src/infrastructure/sqlalchemy/repositories/parametros_regulatorios_repository.py`):** falla con `LookupError` si falta un parámetro. No inventa valores.
- **Tablas (`src/infrastructure/sqlalchemy/models_parametros_regulatorios.py`):**
  - `tarifa_capacidad`: distribuidora, tarifa, periodo, fuente_archivo, fuente_metodo, vigencia_desde, vigencia_hasta, importe, csc_kw. Única por (distribuidora, tarifa, periodo).
  - `factura_verificada`: planta_id, distribuidora, tarifa, periodo, fuente_archivo, fuente_metodo, adquirida_kw o tg phi por bloque (punta, valle, resto). Única por (planta_id, periodo). Sin columnas de vigencia: el período de facturación es su vigencia.
  - `parametro_regulatorio`: clave, valor, distribuidora y tarifa opcionales, vigencia_desde y vigencia_hasta opcionales, fuente_archivo y fuente_metodo.
- **Quién carga una tarifa nueva (propuesta, no implementada):** un script de carga versionado (`scripts/cargar_tarifa.py`) que pide fuente y método, escribe una fila nueva con vigencia y registra el alta en la auditoría de cambios (`RepositorioAuditoriaPort`). Sin pantalla de administración en esta fase. Una fila nunca se edita: un cambio de valor es una fila nueva con vigencia desde.
- **Fuera de esta fase:** los 0,95 de FP (umbral por distribuidora y tarifa). Requiere decidir cómo cada analizador recibe el umbral sin contexto de planta. Ver la lista de dudas al final.

### 3. Casos de Uso & DTOs

- `ConsultarAnaliticaPlantaUseCase(consultar_telemetria, repo_organizaciones=None, repo_parametros=None)`. `_penalizacion_por_periodo` pasa de `staticmethod` a método de instancia y exige `repo_parametros` (RuntimeError si falta).
- Fábrica `get_consultar_analitica_planta_use_case`: recibe `repo_parametros` por `Depends(get_parametros_regulatorios_repository)`, que devuelve el adaptador SQL sobre la `Session` de la request.
- DTOs y contrato HTTP sin cambios (`AnaliticaPenalizacionesPlantaDTO`, ruta `/api/v1/analitica/penalizaciones/planta`).

### 4. Matriz de Pruebas (RED Suite)

Estado honesto: las pruebas de caracterización existían antes del cambio y fijaban los importes. Se mantuvieron las mismas expectativas; solo cambió cómo se llaman las funciones (pasan el repositorio o el factor). No hubo una fase RED explícita para la carga inicial: el test de fidelidad se escribió después de implementar, y compara contra los literales de antes de #111.

| Archivo | Tests | Qué fija | Cambio |
|---|---|---|---|
| `tests/unit/test_parametros_regulatorios.py` (nuevo) | 14 | Carga inicial = literales (valor por valor); SQL = memoria; SQL falla cerrado | nuevo |
| `tests/unit/test_tarifas_distribuidora.py` | 6 | Importe Edesur, recargo 2025-07, sin exceso, sin tarifa | llamadas con repo y factor |
| `tests/unit/test_penalizacion_reactiva_edelap.py` | 4 | Régimen 1992 (0,62) | límite por parámetro; `LIMITE` leído del repo |
| `tests/unit/test_penalizacion_periodo.py` | 5 | Durax y UPP por período | llamadas con repo |
| `tests/unit/test_penalizacion_periodo_endpoint.py` | 3+ | Endpoint por período | override de `get_parametros_regulatorios_repository` |
| `tests/unit/test_analitica_planta.py` | — | Ventana sin período | sin cambios |

### 5. Desglose de Commits Atómicos Planificados

1. `refactor(dominio)`: puerto y funciones puras con datos por parámetro; sin literales en domain.
2. `feat(datos)`: modelos, migración Alembic con carga inicial y adaptador SQL; `alembic/env.py` importa el módulo de modelos.
3. `feat(aplicacion)`: `ConsultarAnaliticaPlantaUseCase` recibe el repositorio; fábrica por `Depends`.
4. `test(tarifas)`: tests de caracterización adaptados a la nueva firma (mismas expectativas), fidelidad de la carga inicial y adaptador SQL.

### 6. Criterios del Gauntlet

- `APP_ENV=test ./scripts/pre-push.sh` en verde (7/7).
- `tests/test_architecture.py` en verde: dominio solo stdlib, `routes/` sin ORM.
- `alembic heads` = `e8a1f3c2b4d6` (sin conectarse a ninguna base).
- `git grep` sin literales de tarifa, factor, límite tg phi ni facturas verificadas en `src/domain` y `src/application`.

**Dudas que quedan para el padre / dueño (no resueltas por la hija):**
1. Los 0,95 de FP (N4): cómo recibe cada analizador el umbral. `analizador_reactiva`, `analizador_calidad_metrologica` y `evaluador_alertas_calidad` no tienen contexto de planta ni de distribuidora. Hay que decidir si el umbral entra como parámetro obligatorio desde la capa de aplicación o si se resuelve en la ingesta.
2. Mapeo planta → distribuidora: `ConsultarAnaliticaPlantaUseCase` necesita saber qué umbral aplica a una planta. Hoy no hay esa relación en el código.
3. Vigencia del factor 1,5 y del límite 0,62: no hay documento de vigencia en el repo. Se cargaron sin `vigencia_desde`.
