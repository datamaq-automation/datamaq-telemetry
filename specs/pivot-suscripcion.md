# Spec: alinear el backend al modelo "plan Free + suscripción única" (Bloque A — borrados)

> **Estado:** aprobada (bloque A) · **Fecha:** 2026-09-15 · **Dueño:** Agustín
> **Decisiones aplicables:** `../decisions/2026-09-15_modelo-comercial-suscripcion-unica.md`,
> `../decisions/2026-09-14_billing-mercadopago.md`
> **Fuente:** `../specs/pivot-suscripcion-backend.md` (spec padre, sección "Repo: datamaq-telemetry")
> **Bloque B (alertas de suscriptor):** bloqueado por la duda 1 del padre. No forma parte de esta spec.

## 1. Objetivo y Contexto

El backend todavía conserva, como código vivo y como docstring, reglas del modelo comercial
anterior ("60 días de PRO por instalación/consultoría" y la bifurcación Free
`VITRINA_ANONIMA` / `PRIVADO_BASICO`) que el modelo vigente ("Free = 7 días sin alertas;
Suscripción única = histórico completo + alertas") ya no contempla. `www-datamaq` vende el
modelo nuevo desde `data/content/planes.yaml`; el backend debe dejar de expresar, ni siquiera
como código muerto o documentación, el modelo viejo — para que ningún desarrollador ni agente
lo reintroduzca de buena fe leyendo una docstring o un test que ya no es verdad.

**Alcance de esta spec (bloque A, desbloqueado):**

1. Eliminar `PoliticaSuscripcionService.calcular_vencimiento_inicial`,
   `extender_por_consultoria` y las constantes `DURACION_INSTALACION_INICIAL_DIAS` /
   `DURACION_CONSULTORIA_DIAS`. Reescribir la docstring de la clase.
2. Eliminar el miembro `ModoFreeTier.VITRINA_ANONIMA` y sus dos ramas en
   `resolver_retencion_dias` / `resolver_intervalo_minimo_segundos`. La política free queda
   con un solo camino: 7 días de retención, 3600 s de intervalo mínimo.
3. Eliminar `docs/to_www-datamaq.md` (describe "Opción A — Vitrina Pública Anonimizada" como
   directiva vigente; ya no cumple función, `www-datamaq` no lo consume).
4. Ajustar los tests que usaban los símbolos eliminados, sin perder cobertura de lo que sigue
   vigente (`es_pro_vigente`, `resolver_retencion_dias`, `resolver_intervalo_minimo_segundos`).

**Explícitamente fuera de alcance (no tocar en esta spec):**

- `GestionarSuscripcionesUseCase.cancelar(modo_free: ModoFreeTier = ...)`: el parámetro queda
  intacto. El padre señala que "puede desaparecer" al quedar un solo modo, pero es una
  observación, no un requisito de este bloque — tocarlo no es necesario para que el código deje
  de expresar el modelo viejo.
- `PlanTelemetria.canales_notificacion`: queda como dato sin consumidor hasta que exista más de
  un canal (bloque B).
- Migración de datos sobre filas `free_tier_mode = 'VITRINA_ANONIMA'` en la DB real: la duda 2
  del padre no está resuelta y **no se corre nada contra la DB de `.env` sin autorización
  explícita**. El fallback ya existente en `MySQLSuscripcionesRepository._to_entity`
  (`try/except ValueError` → `PRIVADO_BASICO`) ya cubre cualquier fila histórica sin cambios de
  código: una fila vieja con ese valor simplemente pasa a comportarse como Free de 7 días la
  próxima vez que se lea. No se agrega ninguna migración de Alembic en esta spec.
- Checkout, webhook, expiración de suscripciones (cerrados en trabajo de billing previo).
- `test_migraciones.py::test_e2_...`: usa `'VITRINA_ANONIMA'` como string SQL crudo para
  probar una migración histórica ya aplicada, no el enum de dominio. No se toca.

## 2. Dominio y Puertos

### `src/domain/telemetria/servicios/politicas_suscripcion.py`

- Eliminar de `PoliticaSuscripcionService`: `DURACION_INSTALACION_INICIAL_DIAS`,
  `DURACION_CONSULTORIA_DIAS`, `calcular_vencimiento_inicial`, `extender_por_consultoria`.
- `_normalizar_utc` se conserva (lo sigue usando `es_pro_vigente`).
- Nueva docstring de clase (reemplaza la actual, que describe 60 días + bifurcación):

  ```python
  class PoliticaSuscripcionService:
      """Reglas de vigencia del plan pago único y de la política Free por defecto.

      Sin PRO vigente, la organización opera en modo Free: 7 días de retención,
      granularidad mínima de 1 hora, sin notificaciones.
      """
  ```

- `resolver_retencion_dias(es_pro, modo_free)` pierde la rama `VITRINA_ANONIMA`:
  ```python
  @staticmethod
  def resolver_retencion_dias(es_pro: bool, modo_free: ModoFreeTier) -> int:
      return 365 if es_pro else 7
  ```
  El parámetro `modo_free` queda sin uso en el cuerpo pero se conserva en la firma: lo llaman
  `consultar_telemetria.py` y `autenticar_usuario.py` posicionalmente junto con `es_pro`, y
  achicar la firma es un cambio de contrato que no pide esta spec (fuera de alcance).
- `resolver_intervalo_minimo_segundos(es_pro, modo_free)` pierde la rama `VITRINA_ANONIMA`:
  ```python
  @staticmethod
  def resolver_intervalo_minimo_segundos(es_pro: bool, modo_free: ModoFreeTier) -> int:
      return 0 if es_pro else 3600
  ```
- Ruff/Pyright: al no usar `modo_free` dentro del cuerpo, verificar que no dispare warning de
  parámetro no usado (ruff no lo marca por defecto para parámetros de función; si lo hiciera,
  no se agrega `_ =` ni se lo renombra con `_`, se lo deja documentado por el tipo).

### `src/domain/telemetria/value_objects.py`

- `ModoFreeTier` pierde el miembro `VITRINA_ANONIMA`. Queda:
  ```python
  class ModoFreeTier(str, Enum):
      PRIVADO_BASICO = "PRIVADO_BASICO"
  ```
- Sin cambios en `ports.py`, `entities.py`, ni en los repositorios de infraestructura
  (`suscripciones_repository.py` ya tolera valores desconocidos vía el fallback documentado
  arriba).

## 3. Casos de Uso y DTOs

Sin cambios de contrato. `ConsultarTelemetriaUseCase._obtener_contexto_suscripcion` y
`AutenticarUsuarioUseCase._resolver_estado_plan` siguen llamando a
`PoliticaSuscripcionService.resolver_retencion_dias(es_pro, sus.modo_free)` /
`resolver_intervalo_minimo_segundos(es_pro, sus.modo_free)` sin modificación: el único cambio es
que `sus.modo_free` ya no puede valer `VITRINA_ANONIMA` (el tipo lo impide en código nuevo; una
fila vieja con ese string cae al fallback de `PRIVADO_BASICO` al leerse).

`GestionarSuscripcionesUseCase` no se modifica (ver "fuera de alcance").

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_domain.py` (líneas ~457-506)

Reemplazar `test_politica_suscripcion_pro_freemium_bifurcado` por una versión sin las
aserciones de vencimiento/consultoría ni de `VITRINA_ANONIMA`, conservando lo que sigue vigente:

```gherkin
Escenario: Política de suscripción sin vencimiento por instalación
  Dado que ya no existen calcular_vencimiento_inicial ni extender_por_consultoria
  Cuando evalúo es_pro_vigente con un vencimiento futuro/pasado/None
  Entonces se comporta igual que antes (vigente si ahora <= vencimiento; False si es None)

Escenario: Retención y granularidad con un solo modo Free
  Dado es_pro=True
  Entonces resolver_retencion_dias == 365 y resolver_intervalo_minimo_segundos == 0
  Dado es_pro=False (único modo_free posible: PRIVADO_BASICO)
  Entonces resolver_retencion_dias == 7 y resolver_intervalo_minimo_segundos == 3600
```

Nombre nuevo: `test_politica_suscripcion_retencion_y_vigencia_pro`. Se conserva intacto
`test_politica_suscripcion_compatibilidad_naive_aware_timezone` (no usa los símbolos
eliminados).

### `tests/unit/test_gestionar_suscripciones.py` (línea ~75)

`test_activar_o_extender_preserva_modo_free_previo` usaba `VITRINA_ANONIMA` solo como un valor
"distinto de PRIVADO_BASICO" para probar que se preserva el `modo_free` previo. Con un solo
miembro en el enum, el test ya no puede distinguir "preserva" de "siempre pisa con el default";
pasa a afirmar lo único que puede afirmar con un solo modo — reemplazar la asignación manual y
las dos aserciones por `ModoFreeTier.PRIVADO_BASICO`, dejando el test como guarda de regresión
de que `activar_o_extender` no pisa el `modo_free` explícitamente aunque hoy solo haya un valor
posible.

### `tests/unit/test_suscripciones_repository.py` (líneas ~32-34)

`test_guardar_crea_y_actualiza` usaba `VITRINA_ANONIMA` en el primer `guardar` para luego
comprobar que un segundo `guardar` con `PRIVADO_BASICO` lo actualiza. Reemplazar
`ModoFreeTier.VITRINA_ANONIMA` por `ModoFreeTier.PRIVADO_BASICO` en la creación inicial (línea
32); la aserción de la línea 34 (`creada.modo_free is ModoFreeTier.PRIVADO_BASICO`) sigue
teniendo sentido como comprobación de ida y vuelta, aunque ya no cambie de valor entre el alta y
la actualización.

### `tests/unit/test_migraciones.py`

Sin cambios: `'VITRINA_ANONIMA'` ahí es un string SQL crudo insertado directamente para probar
una migración de Alembic ya aplicada en producción, no el enum de dominio. Tocarlo sería
reescribir historia de una migración ya corrida.

### Contratos de test (assertions) afectados

- `test_politica_suscripcion_retencion_y_vigencia_pro` (reemplaza a
  `test_politica_suscripcion_pro_freemium_bifurcado`)
- `test_politica_suscripcion_compatibilidad_naive_aware_timezone` (sin cambios)
- `test_activar_o_extender_preserva_modo_free_previo` (ajustado, mismo nombre)
- `test_guardar_crea_y_actualiza` (ajustado, mismo nombre)

## 5. Criterios del Gauntlet

- `bash scripts/pre-push.sh` en verde (integridad, `ruff check .`, `pyright` estricto,
  verificación de arquitectura/DIP, cobertura ≥ 85%).
- `grep -rn "VITRINA_ANONIMA\|calcular_vencimiento_inicial\|extender_por_consultoria\|DURACION_INSTALACION_INICIAL_DIAS\|DURACION_CONSULTORIA_DIAS" src docs` sin resultados (salvo el string crudo en `tests/unit/test_migraciones.py`, que queda fuera del grep por ser `tests/`).
- `docs/to_www-datamaq.md` no existe.
- Cero `# type: ignore`, cero re-exportaciones nuevas, dominio (`src/domain/`) sigue sin
  importar terceros.
- Commits atómicos por paso (sugerido: 1) borrado de `PoliticaSuscripcionService` + test de
  dominio, 2) borrado de `VITRINA_ANONIMA` + los dos tests de infraestructura/aplicación,
  3) borrado de `docs/to_www-datamaq.md`). Conventional Commits (`refactor:` o `docs:` según
  corresponda). No pushear — el dueño aprueba y pushea manualmente.
