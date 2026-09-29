# Spec: Energía registrada de las facturas de EDELAP

> **Estado:** en implementación · **Fecha:** 2026-09-28
> **Origen:** bloque `## Repo: datamaq-telemetry` de `specs/energia-registrada-edelap.md` del repo
> padre, copiado sin cambios (la sección 1 es del padre y no se edita acá).
> **Decisiones aplicables:** `decisions/2026-09-28_energia-registrada-edelap.md` (D1–D6),
> `decisions/2026-09-24_factura-distribuidora-yaml.md` (repo padre).

## Repo: `datamaq-telemetry`

> La sesión iniciada en este repo copia este bloque como `specs/energia-registrada-edelap.md` y
> completa las secciones **2. Dominio & Puertos**, **3. Casos de Uso & DTOs**, **4. Matriz de
> Pruebas (RED Suite)** y **5. Criterios del Gauntlet** siguiendo su `AGENTS.md`. El padre escribe
> **solo** la sección 1.

**Traspasada a hija:** sí (2026-09-28) · **Bloque cerrado:** no

### 1. Objetivo y Contexto

**Objetivo:** que cada documento EDELAP `tipo_dato="potencia"` exponga la energía activa y reactiva
registradas por franja que informa la factura, con nombres propios que no se confundan con la
energía facturada.

**Alcance:**
- Entidad `FacturaDistribuidora`: campos nuevos `energia_registrada_punta_kwh`,
  `energia_registrada_resto_kwh`, `energia_registrada_valle_kwh`, `energia_registrada_total_kwh`,
  `energia_reactiva_punta_kvarh`, `energia_reactiva_resto_kvarh`, `energia_reactiva_valle_kvarh`
  (nombres propuestos por D2; la hija puede ajustarlos en §2 y lo reporta). Docstring con el
  contrato de D3: "un documento de potencia trae potencia y, si la factura la informa, la energía
  registrada; nunca energía facturada".
- `energia_facturada_kwh` **no** mira los campos nuevos: en un documento EDELAP sigue en `None`.
- `ParserFacturaPotenciaEdelap` (`src/infrastructure/pdfplumber/parser_factura_distribuidora.py`,
  237 líneas): extraer el bloque "Lecturas". D6: si punta+resto+valle ≠ "Total de energía activa"
  impreso, el parser falla con `FacturaDistribuidoraIlegibleError`.
- `sge_mapper.py` (`factura_to_dto`) y `FacturaDistribuidoraResponseDTO` (`sge_dto.py:128`):
  campos camelCase `energiaRegistrada{Punta,Resto,Valle,Total}Kwh`,
  `energiaReactiva{Punta,Resto,Valle}Kvarh`. Cambio **aditivo**.
- `verificador_facturas.py` (`_magnitudes_negativas`, línea 15): incluir los campos nuevos. Si es
  barato, verificar también la coherencia suma de franjas = total en el YAML.
- Regenerar las 12 filas de `datamaq-data/facturas_distribuidora.yml` con
  `scripts/importar_factura_distribuidora.py` y cruzar cada total contra el PDF.
- Fixtures: `extract_text()` literal de PDFs reales (`AGENTS.md` §3). Como mínimo 2024-11 y un
  mes sin exceso (2024-02).
- Actualizar `docs/informe-cambios-contrato-facturas.md` con los campos nuevos para el front.

**Fuera de alcance:** costo estimado y balance (D4, siguen leyendo solo `tipo_dato == "energia"`);
los cargos variables de transporte; migraciones (las facturas viven solo en el YAML,
`infrastructure/yaml/loaders.py:187`); el parser de CAMMESA.

**Certezas verificadas en este repo:**
- Hoy el parser ya lee las filas "Potencia punta/resto/valle" del mismo medidor
  (`parser_factura_distribuidora.py:95-107`); las de energía están en el mismo bloque.
- `entities.py` tiene 136 líneas, `sge_dto.py` 276: margen de sobra para el límite de 500.
- Tests existentes a tocar: `tests/unit/test_parser_factura_distribuidora.py`,
  `test_factura_distribuidora.py`, `test_verificador_facturas.py`.

**Ya hecho por el padre (no repetir):** nada en código. La decisión quedó aprobada con las
correcciones del punto físico y de `formatearEnergia`.

**Push:** requiere autorización del dueño, igual que el de `datamaq-data`. El bloque de
`app-datamaq` no arranca contra producción hasta que esto esté desplegado.


### 2. Dominio & Puertos

**Certezas adicionales verificadas en esta sesión** (`extract_text()` de los 12 PDFs de
`data/Papelera platense - EDELAP/`, 2023-12 a 2024-11):

- Las 12 facturas traen las 6 filas de lectura de energía del medidor 241609298 con marca `R`, y en
  las 12 la suma punta + resto + valle de la activa coincide exacto con el "Total de energía
  activa" impreso.
- **2024-02 trae cada fila duplicada** por el cambio de medidor (el mismo que ya duplica las filas de
  potencia): una con el consumo real y otra con las lecturas iguales y consumo 0
  (`241609298 Energia activa punta 95852 95852 18.000 0 R`). También trae dos veces el renglón
  "Total de energía activa: 202122KWh", con el mismo valor. Para la potencia (una demanda) se toma el
  máximo; **la energía se suma**, porque es acumulable. Con 0 da lo mismo, y es lo correcto si
  alguna vez el consumo del mes se reparte entre el medidor viejo y el nuevo.
- Los tres fixtures de EDELAP que ya existen en `tests/unit/test_parser_factura_distribuidora.py`
  (2024-11, 2023-12, 2024-02) son idénticos, línea por línea, al `extract_text()` de sus PDFs
  (comparado por programa en esta sesión). Se reusan: no hace falta agregar fixtures.

**Entidad** `FacturaDistribuidora` (`src/domain/sge/entities.py`). Los nombres de D2 se mantienen
sin cambios. Siete campos opcionales nuevos, todos `float | None = None`:

| Campo | Unidad | Fuente en la factura |
|---|---|---|
| `energia_registrada_punta_kwh` | kWh | "Energia activa punta" (consumo) |
| `energia_registrada_resto_kwh` | kWh | "Energia activa resto" |
| `energia_registrada_valle_kwh` | kWh | "Energia activa valle" |
| `energia_registrada_total_kwh` | kWh | "Total de energía activa" impreso |
| `energia_reactiva_punta_kvarh` | kVArh | "Energia Reactiva Punta" |
| `energia_reactiva_resto_kvarh` | kVArh | "Energia Reactiva Resto" |
| `energia_reactiva_valle_kvarh` | kVArh | "Energia Reactiva Valle" |

- `energia_registrada_total_kwh` es un campo, no una propiedad calculada: guarda el total impreso,
  que es lo que permite que el verificador cruce la suma de franjas contra el documento (D6).
- `energia_facturada_kwh` y `valor_energia_ars_kwh_promedio` **no cambian** ni leen los campos
  nuevos: en un documento EDELAP siguen en `None`.
- El docstring pasa a decir el contrato de D3: "un documento de potencia trae potencia y, si la
  factura la informa, la energía registrada; nunca energía facturada".
- Sin puertos nuevos. `ParserFacturaDistribuidoraPort` no cambia de firma.
- No hay migración: las facturas viven solo en el YAML.

**Parser** `ParserFacturaPotenciaEdelap` (`src/infrastructure/pdfplumber/parser_factura_distribuidora.py`).
Una función privada `_energia_registrada(texto, ruta_pdf)` lee el bloque "Lecturas":

1. **Qué lee de cada fila.** Toma solo las líneas que empiezan con el número de medidor seguido de
   "Energia". De cada una lee únicamente desde el medidor hasta la marca:
   `^(\d+) Energia (activa|Reactiva) (punta|resto|valle) <ant> <act> <constante> <consumo> <marca>`,
   con la franja sin distinguir mayúsculas y la marca como el primer token después del consumo.
   Lo que viene después (la columna de cargos que `extract_text()` pega de otro renglón) no se lee.
2. **Filas rotas.** Una línea `^\d+ Energia …` que no respeta ese formato →
   `FacturaDistribuidoraIlegibleError`. No se saltea en silencio.
3. **Marca.** Distinta de `R` → `FacturaDistribuidoraIlegibleError` con la marca y la fila. No se
   adivina qué significa una "E" (estimada).
4. **Suma.** Por (activa/reactiva, franja) se suman todas las filas, lo que cubre las duplicadas de
   2024-02.
5. **Total impreso.** Todas las apariciones de `Total de energ[ií]a activa: <n>KWh` tienen que dar el
   mismo valor. Si hay más de un valor distinto → error.
6. **Coherencia (D6).** Si hay filas de activa, tienen que estar las tres franjas y el total
   impreso, y punta + resto + valle tiene que ser igual al total. Si no → error. Si la reactiva
   aparece, tienen que estar sus tres franjas, o error.
7. **Factura sin el dato.** Si no hay ninguna fila de lectura de energía **ni** total impreso, los
   siete campos quedan en `None`: es el caso "la factura no lo informa" de D3. Si hay total sin
   filas, o filas sin total → error.

Los "Cargo Variable … Transp." no se leen (fuera de alcance, D1).

### 3. Casos de Uso & DTOs

- **Sin casos de uso nuevos ni cambios en los existentes.** `consultar_costo_estimado.py` y
  `consultar_balance_energia.py` siguen filtrando `tipo_dato == "energia"` (D4). Se agrega un test
  de regresión que lo fija para el costo estimado.
- **`FacturaDistribuidoraResponseDTO`** (`src/application/dtos/sge_dto.py`): siete campos
  opcionales nuevos, con el mismo patrón de alias que el resto:
  `energiaRegistradaPuntaKwh`, `energiaRegistradaRestoKwh`, `energiaRegistradaValleKwh`,
  `energiaRegistradaTotalKwh`, `energiaReactivaPuntaKvarh`, `energiaReactivaRestoKvarh`,
  `energiaReactivaValleKvarh`. Cada uno lleva un `description` que dice que es la lectura del
  medidor de la distribuidora y no la energía facturada, porque el OpenAPI hoy no tiene semántica
  para esta DTO (informe §4). Cambio aditivo: ningún campo existente cambia.
- **`factura_to_dto`** (`src/application/mappers/sge_mapper.py`): copia los siete campos.
- **Repositorio YAML** (`YamlOrganizacionesRepository._parsear_factura`,
  `src/infrastructure/yaml/repositories/organizaciones_repository.py`): lee los siete campos con
  `_float_opt`. Este archivo no estaba en el alcance de la sección 1, pero sin él los datos del YAML
  no llegan a la entidad.
- **Verificador** (`src/infrastructure/yaml/verificador_facturas.py`). Advierte, no bloquea, como
  hoy:
  - `_magnitudes_negativas` incluye los siete campos.
  - Nueva regla de coherencia: si aparece cualquiera de los cuatro campos de energía registrada
    activa, tienen que estar los cuatro y la suma de franjas tiene que coincidir con el total
    (tolerancia 0,5 kWh, porque el YAML guarda floats).
  - Nueva regla D1: un documento `tipo_dato="energia"` con energía registrada es inválido. La
    registrada va solo en el documento de la distribuidora.
- **Script** `scripts/importar_factura_distribuidora.py`: `_bloque_yaml` emite los siete campos
  cuando no son `None`.
- **Datos** (`datamaq-data`): se regeneran las 12 filas con el script, y el diff tiene que ser solo
  **aditivo** (los campos que ya existen, sin cambios). Cada total se cruza contra el
  "Total de energía activa" de su PDF. Se agrega `*.pdf` al `.gitignore` de `datamaq-data`.

### 4. Matriz de Pruebas (RED Suite)

| # | Archivo | Caso | Espera |
|---|---|---|---|
| 1 | `test_parser_factura_distribuidora.py` | 2024-11 real | registrada 68310/187506/59994, total 315810; reactiva 29538/83304/23202; `energia_facturada_kwh is None`, `energia_activa_*` en `None`, `importe_energia_ars is None` |
| 2 | ídem | 2023-12 real | 76914/191304/90954, total 359172; reactiva 37152/92034/44730 |
| 3 | ídem | 2024-02 real (filas duplicadas en 0, total impreso dos veces) | 47826/103086/51210, total 202122; reactiva 9378/20124/9792 |
| 4 | ídem | 2024-11 con la marca de "Energia activa punta" cambiada a `E` | `FacturaDistribuidoraIlegibleError` |
| 5 | ídem | 2024-11 con el total impreso cambiado (315811) | `FacturaDistribuidoraIlegibleError` (D6) |
| 6 | ídem | 2024-11 sin la fila "Energia activa valle" | `FacturaDistribuidoraIlegibleError` |
| 7 | ídem | 2024-11 sin ninguna fila de energía ni total | los siete campos en `None`; la potencia se sigue leyendo |
| 8 | ídem | 2024-11 con una fila `241609298 Energia activa punta` mal formada | `FacturaDistribuidoraIlegibleError` |
| 9 | `test_factura_distribuidora.py` | entidad solo con `energia_registrada_*` | `energia_facturada_kwh is None`, `valor_energia_ars_kwh_promedio is None` |
| 10 | ídem | YAML con los siete campos → repositorio | la entidad los trae como `float` |
| 11 | ídem | `factura_to_dto` + `model_dump(by_alias)` | claves `energiaRegistrada*Kwh` / `energiaReactiva*Kvarh` con valor; `energiaFacturadaKwh: None` |
| 12 | `test_verificador_facturas.py` | registrada coherente | 0 inválidas |
| 13 | ídem | suma de franjas ≠ total | 1 inválida |
| 14 | ídem | total sin franjas (incompleta) | 1 inválida |
| 15 | ídem | registrada negativa | 1 inválida |
| 16 | ídem | documento `energia` con registrada | 1 inválida (D1) |
| 17 | test existente de costo estimado | planta con un documento de potencia con registrada y ninguno de energía | el costo de energía sigue en "s/d" (D4) |

Las variantes de los casos 4 a 8 se derivan **por programa** del fixture literal (reemplazando un
token puntual), no se retipean. Así el resto del texto sigue siendo el real.

### 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` en verde: integridad, ruff, pyright, tests unitarios con cobertura ≥ 85 %.
  La salida se redirige a un archivo, no se canaliza.
- Los unitarios, además, con `DB_HOST=127.0.0.2 DB_PORT=1`, para reproducir el CI sin MySQL.
- `scripts/verify_architecture.py` y `verify_code_size.py`: dominio solo stdlib y ningún archivo de
  `src/` de más de 500 líneas (el parser pasa de 237 a unas 300).
- `verificar_facturas_plantas()` contra el `data/` real: 0 inválidas.
- Cruce manual: para cada uno de los 12 períodos, `energia_registrada_total_kwh` del YAML es igual al
  "Total de energía activa" del PDF, y el diff del YAML es solo aditivo.
- Commits atómicos en español en los dos repos. **Sin push** de ninguno de los dos sin autorización
  del dueño.
