# Spec: Tarifas y parámetros regulatorios en SQL (fase 1)

> Sección 1: copia del bloque de telemetry del spec del repo padre (escrita por el padre, verificada en cc34c26).
> Secciones 2 a 6: describen lo mergeado en `refactor/issue-111-tarifas-en-sql` (PR #123 y commits de revisión).
> Issue: datamaq-automation/datamaq#111 · Decisión: decisions/2026-10-31_tarifas-y-parametros-regulatorios-en-sql.md (repo padre)

## Repo: `datamaq-telemetry`

> La sesión iniciada en este repo copia este bloque como `specs/tarifas-en-sql.md` del repo y completa las secciones **2. Dominio & Puertos**, **3. Casos de Uso & DTOs**, **4. Matriz de Pruebas (RED Suite)**, **5. Desglose de Commits Atómicos Planificados** y **6. Criterios del Gauntlet** siguiendo su `AGENTS.md`. El padre escribe **solo** la sección 1.

**Traspasada a hija:** no · **Bloque cerrado:** no

### 1. Objetivo y Contexto

**Objetivo:** que ningún precio, parámetro regulatorio ni factura verificada viva como literal en `domain` ni en `application`. Pasan a tablas SQL versionadas por vigencia, con distribuidora, tarifa y fuente (documento y método de carga). Esto cierra la infracción R2 de la auditoría del SRS (Regla 4, parámetros críticos fuera del código).

**Alcance:**
- Tablas con vigencia desde/hasta, distribuidora, tarifa, `fuente_archivo` y método de carga, para: (a) el precio de capacidad por período; (b) los períodos con factura verificada; (c) los parámetros regulatorios que hoy son constantes con nombre (factor de recargo por exceso y límite de tg φ del régimen de 1992), cada uno con la distribuidora y la tarifa donde se aplica.
- Puerto en `domain` (solo stdlib) para consultar esos datos, adaptador SQLAlchemy en `infrastructure`, y cableado por inyección (`Depends`) sin tocar `routes/` con ORM (el gate de controladores delgados está activo desde #121).
- Migración Alembic que crea las tablas y carga las filas de hoy, con su fuente, **idénticas** a los literales actuales.
- **Los 0,95 de FP quedan fuera de la fase 1** (ajuste del padre, 2026-10-31, tras el PROGRESO de la hija). No hay mapeo planta → distribuidora: la acometida declara `categoria_tarifaria` (`entities.py:137`) pero no la distribuidora, y el analizador de ingesta no tiene contexto de planta. El umbral por distribuidora (N4) depende de M-1 y va en la fase 2. La tabla de parámetros queda lista para alojarlo.

**Fuera de alcance:**
- Cambiar cualquier valor de facturación. Ninguno cambia sin decisión del dueño.
- El umbral de FP por distribuidora (N4) y declarar la distribuidora en la acometida (M-1, toca también `datamaq-data`).
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

- **Puerto** (`src/domain/telemetria/parametros_regulatorios.py`, solo stdlib): `RepositorioParametrosRegulatoriosPort` con
  - `obtener_tarifa_capacidad(distribuidora, periodo)`,
  - `obtener_factura_verificada(planta_id, periodo)`,
  - `factor_recargo_exceso(distribuidora, tarifa)` y `limite_tg_fi_regimen_1992(distribuidora, tarifa)`.
  Los tipos `TarifaCapacidad` y `FacturaVerificada` van por `TYPE_CHECKING`: sin ciclos en runtime.
- **Funciones puras** (quedan en dominio, reciben datos por parámetro):
  - `obtener_tarifa_capacidad(repo, distribuidora, periodo)`: delega en el puerto.
  - `calcular_recargo_exceso_potencia(csc_kw, adquirida_kw, tarifa, factor_recargo)`.
  - `calcular_penalizacion_reactiva_edelap(periodo, fuente_archivo, tg_fi_por_bloque, limite_tg_fi)`. El texto del régimen se arma desde `limite_tg_fi`.
  - `calcular_penalizacion_periodo(repo, planta_id, periodo)`. Un `LookupError` del repositorio (parámetro faltante, p. ej. una tarifa escrita distinto) devuelve el período sin cifra y con `MOTIVO_PERIODO_SIN_TARIFA`; no es un error del sistema.
- **Literales fuera de `domain`:** `_TARIFAS_CAPACIDAD`, `FACTOR_RECARGO_EXCESO`, `LIMITE_TG_FI_REGIMEN_1992` y `_FACTURAS_VERIFICADAS`. Verificado con `git grep`: ningún valor de la carga inicial queda en `src/domain` ni `src/application`.
- **Repositorio en memoria** (`src/adapters/gateways/in_memory_parametros_regulatorios.py`): la misma carga inicial (`parametros_regulatorios_iniciales.py`), para tests de dominio y aplicación.
- **Adaptador SQLAlchemy** (`src/infrastructure/sqlalchemy/repositories/parametros_regulatorios_repository.py`): elige la fila vigente más reciente. Si falta un parámetro, falla con `LookupError`: no inventa valores.
- **Tablas** (`src/infrastructure/sqlalchemy/models_parametros_regulatorios.py`):
  - `tarifa_capacidad`: distribuidora, tarifa, periodo, fuente_archivo, fuente_metodo, vigencia_desde, vigencia_hasta, importe, csc_kw. **Única por (distribuidora, tarifa, periodo, vigencia_desde)**. Una corrección es una fila nueva con otra vigencia_desde.
  - `factura_verificada`: planta_id, distribuidora, tarifa, periodo, fuente_archivo, fuente_metodo, adquirida_kw o tg phi por bloque. **Única por (planta_id, periodo, fuente_archivo)**. Una corrección es otra fila; gana la de id más alto. No tiene columnas de vigencia: el período de facturación es su vigencia.
  - `parametro_regulatorio`: clave, valor, distribuidora y tarifa (alcance), vigencia_desde y vigencia_hasta opcionales, fuente_archivo, fuente_metodo. Sin unicidad: gana la fila de id más alto para (clave, distribuidora, tarifa).
- **Migración** `e8a1f3c2b4d6` (sobre `d5f2a9c1e7b3`): crea las tablas y carga los datos **congelados dentro del archivo de la migración** (no se importan de `src/`). Test que compara las filas contra valores escritos a mano.
- **Alcance de los parámetros cargados:**
  - `factor_recargo_exceso` = 1,5, asociado a Edesur T3 MT. Fuente: renglón "Recargo Exceso Potencia T3" de la factura 2025-07, `transcripcion_verificada`.
  - `limite_tg_fi_regimen_1992` = 0,62, asociado a EDELAP T5M12. Fuente: decisión registrada `decisions/2026-10-14_regimen-reactiva-edelap.md` (contrato nacional de 1992), no una transcripción de documento.
  - `vigencia_desde` vacía en ambos: no hay documento de vigencia en el repo.
- **Quién carga una tarifa nueva:** `scripts/cargar_tarifa.py`. Simulación por defecto; escribe solo con `--aplicar`; una corrección es una fila nueva con otra vigencia. **No registra auditoría todavía** (seguimiento datamaq#112). Aplicarlo en la base real es decisión del dueño con DevOps; los tests usan SQLite.
- **Fuera de esta fase:** los 0,95 de FP por distribuidora y tarifa (fase 2, con M-1; el régimen y la distribuidora de cada planta todavía no existen en el esquema), `esquema_potencia`, la fórmula de `consultar_costo_estimado.py:139-142` y `data/facturas_distribuidora.yml`.

### 3. Casos de Uso & DTOs

- `ConsultarAnaliticaPlantaUseCase(consultar_telemetria, repo_organizaciones=None, repo_parametros=None)`. `_penalizacion_por_periodo` es un método de instancia; lanza `RuntimeError` si falta `repo_parametros`.
- La fábrica `get_consultar_analitica_planta_use_case` recibe `repo_parametros` por `Depends(get_parametros_regulatorios_repository)`, que es el adaptador SQL sobre la `Session` de la request.
- R2a: la comparación del FP en el razonamiento de "no recomendar banco" usa `_FP_LIMITE_PENALIZACION` (mismo valor, sin cambio de comportamiento).
- DTOs y contrato HTTP sin cambios.

### 4. Matriz de Pruebas (RED Suite)

Estado honesto: las pruebas de caracterización existían antes del cambio. Se mantuvieron sus expectativas; cambió la forma de llamar a las funciones (pasan el repositorio o el factor). El test de fidelidad y el de migración se escribieron después de implementar: comparan contra literales escritos a mano, no contra el código.

| Archivo | Tests | Qué fija |
|---|---|---|
| `tests/unit/test_parametros_regulatorios.py` | 20 | carga inicial = literales; SQL = memoria; SQL falla cerrado; correcciones por vigencia; parámetro faltante y tarifa distinta dan sin cifra; texto del régimen sigue al límite |
| `tests/unit/test_migracion_parametros_regulatorios.py` | 4 | `upgrade head` deja las filas esperadas; `downgrade` borra las tres tablas |
| `tests/unit/test_cargar_tarifa.py` | 6 | simulación sin escribir; `--aplicar` inserta y el adaptador la ve; datos inválidos no escriben |
| `tests/unit/test_tarifas_distribuidora.py` | 6 | mismas expectativas; llamadas con repo y factor |
| `tests/unit/test_penalizacion_reactiva_edelap.py` | 4 | mismas expectativas; límite leído del repo |
| `tests/unit/test_penalizacion_periodo.py` | 5 | mismas expectativas; llamadas con repo |
| `tests/unit/test_penalizacion_periodo_endpoint.py` | 3+ | mismas expectativas; override de `get_parametros_regulatorios_repository` con el repo de memoria |
| `tests/unit/test_migraciones.py` | — | `REVISION_HEAD` = `e8a1f3c2b4d6` (cabeza nueva; sin cambio de expectativa de esquema) |

### 5. Commits (rama `refactor/issue-111-tarifas-en-sql`, PR #123)

1. `a6069be` refactor(datos): puerto, adaptador, modelos, migración, use case, fábrica y tests de caracterización.
2. `ea170e5` refactor(aplicacion): R2a.
3. `6eb7ad3` feat(scripts): `scripts/cargar_tarifa.py` y sus tests.
4. `a8fb8e9` fix(dominio): parámetro faltante o tarifa escrita distinto dan sin cifra, no 500; texto del régimen desde el límite; también incluyó el cambio de `fuente_metodo` del 0,62 en la semilla (quedó en este commit y no en el de la migración).
5. `ed51bb8` fix(migracion): datos congelados dentro de la migración; test de filas.

### 6. Criterios del Gauntlet

- `APP_ENV=test ./scripts/pre-push.sh` en verde (7/7).
- `tests/test_architecture.py` en verde: dominio solo stdlib; `routes/` sin ORM.
- `alembic heads` = `e8a1f3c2b4d6` (sin conectarse a ninguna base). La migración no importa de `src/`.
- `git grep` sin valores de la carga inicial en `src/domain` ni `src/application`.

**Dudas abiertas (fase 2):** los 0,95 de FP por distribuidora y tarifa; el mapeo planta → distribuidora (no existe en el esquema de la acometida); la auditoría del script (datamaq#112).
