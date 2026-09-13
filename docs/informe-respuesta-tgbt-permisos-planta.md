# Respuesta al Informe de Delegación — Jerarquía TGBT y Permisos de Planta

> **De:** equipo Backend (`datamaq-telemetry`)
> **Para:** equipo Frontend (`app-datamaq`)
> **Fecha:** 2026-09-13
> **Responde a:** "Jerarquía TGBT y permisos de planta en el selector de equipo" (R-01, R-02, R-03), 2026-09-13
> **Tipo de cambio:** R-02 y R-03 aditivos. R-01 **cambia datos de topología** (no el DTO): ver §2.3.

---

## 1. Resumen para quien no quiera leer el resto

Los tres requerimientos están implementados y desplegables. Pero R-01 no era lo que el informe describía: **la jerarquía del unifilar nunca vivió en MySQL**, así que la auditoría por `DESCRIBE`/`information_schema` no podía encontrarla. Vive en `data/organizaciones.yml` (modelo declarativo ISA-95, GitOps) y ya soportaba `tipo: tgbt` y `parent_id` — el contrato que pedían para `GET /unifilar` es el que ya existía. Lo que faltaba era **declarar** los TGBT en las plantas reales y cerrar el vocabulario de `tipo`.

| Req. | Estado | Qué cambia para el frontend |
|---|---|---|
| R-01 TGBT | ✅ Hecho, sin migración | Durax y UPP ahora tienen nodos `tgbt` **con el medidor** y los `transformador` pasan a ser virtuales. `tipo` es vocabulario cerrado. |
| R-02 Plantas por usuario | ✅ Hecho, migración `n8o9p0q1r2s3` | `GET /auth/me` devuelve `plantas[]` y `planta_activa_id`. Endpoints de administración nuevos. |
| R-03 Nombre de máquina | ✅ Hecho | Cada nodo del unifilar trae `nombre_maquina` (`string \| null`). |

---

## 2. R-01 — Nivel TGBT

### 2.1 Por qué el diagnóstico no aplicaba

`device_groups`, `facilities`, `facility_zones` y `machines` existen en MySQL, pero **ninguna de esas tablas es la fuente del árbol unifilar**. La tabla `unifilar_nodes` fue eliminada (migración `k5l6m7n8o9p0_drop_unifilar_nodes_table`) cuando la topología se movió al YAML declarativo. `GET /api/v1/plantas/{id}/unifilar` lee `data/organizaciones.yml → plantas[].nodos_unifilar[]`, cuyo dominio (`TipoNodoUnifilar`) ya tenía:

```
acometida | transformador | tgbt | seccional | carga
```

con `parent_id`, `device_id` y `es_virtual` (= `device_id == null`). Ninguna de las dos opciones de modelado del informe (tabla `distribution_boards` o `parent_group_id`) era necesaria; ambas habrían creado una segunda fuente de verdad en paralelo al YAML.

### 2.2 Qué sí faltaba, y se hizo

1. **Declarar los TGBT.** Ninguna planta los tenía: Durax y UPP declaraban `acometida (MT, virtual) → transformador (380 V, con medidor)`. Con la nomenclatura acordada ("TGBT = la medición aguas abajo del trafo"), ese medidor estaba puesto en el nodo equivocado.
2. **Cerrar el vocabulario.** `NodoUnifilarDTO.tipo` era `z.string()`-equivalente del lado backend (`str`). Ahora es `Literal["acometida", "transformador", "tgbt", "seccional", "carga"]`; un `PUT /unifilar` con otro valor responde `422`.

> **Sobre `alimentador`:** no se agregó como tipo. Lo que el informe llama "alimentador" (un `device_group` plano bajo la planta) no es un nodo del unifilar; en el árbol eléctrico eso es un `seccional` (tablero seccional) o una `carga`. Si necesitan distinguirlos en UI, díganlo y evaluamos un tipo nuevo — pero no en paralelo a `seccional`.

### 2.3 Topología resultante — **esto es lo que los rompe si no lo miran**

```
acometida MT   (virtual, 13,2 kV)          es_virtual: true,  device_id: null
└── transformador (virtual, 380 V)         es_virtual: true,  device_id: null   ← ANTES tenía el medidor
    └── tgbt (380 V)                       es_virtual: false, device_id: "…"    ← NUEVO, tiene el medidor
```

Nodos concretos:

| Planta | Trafo (ahora virtual) | TGBT nuevo (con `device_id`) |
|---|---|---|
| Durax | `nodo-durax-trifasico-1` "Trafo Usina" | `nodo-durax-tgbt-usina` "TGBT Usina" |
| Durax | `nodo-durax-powermeter-bf2c` "Trafo Horno" | `nodo-durax-tgbt-horno` "TGBT Horno" |
| UPP | `nodo-upp-trafo-arriba` "Trafo Arriba" | `nodo-upp-tgbt-arriba` "TGBT Arriba" |
| UPP | `nodo-upp-trafo-abajo` "Trafo Abajo" | `nodo-upp-tgbt-abajo` "TGBT Abajo" |

Consecuencias observables:

* `GET /unifilar` de Durax y UPP devuelve **5 nodos en vez de 3**.
* `DispositivoResponseDTO.nodo_unifilar_id` de esos cuatro medidores **cambia** al id del TGBT.
* `GET /api/v1/plantas/{id}/unifilar/nodos/{nodo_id}/…` (agregación) sigue funcionando para el trafo y la acometida: un nodo virtual suma los medidores frontera aguas abajo (`ArbolUnifilarService.medidores_frontera`), así que el trafo devuelve exactamente lo mismo que antes, ahora vía su TGBT.
* `uso_significativo` y `categoria_uso` (ISO 50001) se movieron al TGBT, que es el punto medido.
* `potencia_nominal_kw` de los trafos **se eliminó**: los valores que había (300/150 kW Durax, 800/800 UPP) no salían de ninguna placa — los inventó un LLM. Regla nueva en `CONVENTIONS.md` §3.6: sin fuente verificable, sin campo. El frontend recibe `null` y no debe interpretarlo como 0.
* La planta "Casa" (medidor doméstico, 220 V) **no cambia**: no tiene trafo ni TGBT.

### 2.4 Sobre el ejemplo del informe

El JSON de ejemplo colgaba el TGBT de `"parent_id": "area-horno"`. `area-*` son **zonas del layout 2D** (`GET /layout`), no nodos del unifilar. Son dos árboles distintos: el unifilar es eléctrico (qué alimenta a qué), el layout es espacial (dónde está cada cosa en el plano). `parent_id` de un nodo del unifilar siempre apunta a otro nodo del unifilar. Para el selector de tres niveles, "Área" debería salir del layout (`zonas[]`) y "TGBT" del unifilar (`nodos[].tipo == "tgbt"`); el puente entre ambos es el `device_id`.

---

## 3. R-02 — Plantas por usuario

### 3.1 Modelo

Tabla `user_facility_access` (migración `n8o9p0q1r2s3`), tal como la propusieron, más `created_at` para que el orden de asignación sea determinista:

```sql
CREATE TABLE user_facility_access (
  user_id     VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  facility_id VARCHAR(36) NOT NULL,          -- sin FK: las plantas son SSOT del YAML
  can_switch  TINYINT(1)  NOT NULL DEFAULT 0,
  created_at  DATETIME    NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, facility_id)
);
```

### 3.2 Reglas (respuesta a la duda sobre `superadmin`)

Se resolvió con regla de negocio por rol, no con filas explícitas — `PoliticaAccesoPlantasService`, en este orden:

1. **`superadmin` e `invitado_global`:** todas las plantas de todas las organizaciones, siempre `puede_cambiar: true`. La tabla no aplica.
2. **Usuario con filas:** solo esas plantas, acotadas a su organización (una fila que apunte a otra org se ignora), con el `can_switch` de cada fila, en orden de asignación.
3. **Usuario sin filas:** todas las plantas de su organización con `puede_cambiar: true`. Es el comportamiento histórico, por eso **la migración no necesita backfill** y no cambia nada para nadie hasta que un admin asigne plantas.

`planta_activa_id` = la primera de la lista (`null` si está vacía). "Planta fija" = una sola fila con `can_switch = 0`.

### 3.3 Contrato — `GET /api/v1/auth/me` (extendido, aditivo)

```json
{
  "usuario": "operador.horno@datamaq.com.ar",
  "rol": "operador",
  "totp_enabled": false,
  "organizacion_id": "cf82b4be-0798-4beb-8978-2a27612d5761",
  "organizacion_nombre": null,
  "plantas": [
    { "id": "c64fd625-0037-4caa-b68a-800e8e0ee548", "nombre": "Planta Principal Durax",
      "organizacion_id": "cf82b4be-0798-4beb-8978-2a27612d5761", "puede_cambiar": false }
  ],
  "planta_activa_id": "c64fd625-0037-4caa-b68a-800e8e0ee548"
}
```

Diferencia con lo que pidieron: cada planta trae también `organizacion_id`, porque para `superadmin` la lista cruza organizaciones y el selector necesita agruparla.

### 3.4 Administración (no lo pidieron, pero sin esto la tabla no se puede llenar)

| Método | Ruta | Acceso | Cuerpo / Respuesta |
|---|---|---|---|
| `GET` | `/api/v1/usuarios/{usuario_id}/plantas` | `admin` (misma org) o `superadmin` | → `PlantaAccesoDTO[]` (lo mismo que verá ese usuario en `/me`) |
| `PUT` | `/api/v1/usuarios/{usuario_id}/plantas` | `admin` (misma org) o `superadmin` | `{"plantas": [{"planta_id": "…", "puede_cambiar": false}]}` → `PlantaAccesoDTO[]` |

`PUT` **reemplaza** el conjunto completo (idempotente). `{"plantas": []}` restaura el comportamiento por defecto. Errores: `403` si el admin es de otra organización, `404` si el usuario no existe o una `planta_id` no pertenece a su organización (en ese caso no se escribe nada).

---

## 4. R-03 — `nombre_maquina`

Cada `NodoUnifilarDTO` trae `nombre_maquina: string | null`: el nombre de la máquina asociada 1:1 al `device_id` del nodo (`machines.device_id` es `UNIQUE`), o `null` si el nodo es virtual o el medidor no tiene máquina. Se resuelve con una sola consulta por planta. Coincidimos: "Máquina" no es un nivel del árbol, es un alias del medidor.

---

## 5. Sobre `docs/contratos-api.md` §8.2

El informe cita ese documento como fuente de `tipo`/`parent_id`. No existe en `datamaq-telemetry`; el contrato de este repo para el frontend es [`docs/frontend-integration-guide.md`](frontend-integration-guide.md) (§2.2.1 y §7 actualizados con todo lo de arriba). Si `contratos-api.md` vive en `app-datamaq`, conviene alinearlo con la guía.

---

## 6. Sobre el glosario "Lenguaje ubicuo de planta"

El mapa de contextos es correcto en lo importante — **el punto de unión es siempre `Dispositivo`, no un nivel intermedio** — y la regla de un término por concepto es la que este repo ya sigue. Pero varias filas del glosario heredan el mismo error del informe: buscan la jerarquía eléctrica en MySQL.

| Término del glosario | Decía | Estado real en backend |
|---|---|---|
| Cadena "Eléctrico / Unifilar" | `facilities → facility_zones → device_groups → devices`, "esquema real, vacío" | El unifilar es `data/organizaciones.yml → nodos_unifilar[]` con `tipo`/`parent_id`: `acometida → transformador → tgbt`. **No está vacío**: Durax y UPP tienen 5 nodos cada una. |
| **Área** (eléctrica) = `facility_zones`, "vacío" | — | Son las `zonas[]` de `GET /layout`, declaradas en el YAML (`area-durax-trafo-1`, `area-upp-papelera`, …). **No están vacías.** Y el backend ya las llama **Zona** (`ZonaPlantaDTO`, `LayoutPlantaDTO.zonas`), nunca "Área". |
| **Alimentador** = `device_groups` | nivel del árbol eléctrico | `device_groups` es una agrupación plana, sin `parent_id`, sin relación con el unifilar. No es un nivel del árbol. Lo que eléctricamente cuelga de un TGBT se declara como `seccional` o `carga`. |
| **TGBT** | "plan, pedido a backend" | **Real** desde hoy (§2). |
| `docs/contratos-api.md` §8.2 | fuente del renombre `linea_id → nodo_unifilar_id` | No existe en este repo (§5). El campo `nodo_unifilar_id` sí existe en `DispositivoResponseDTO`. |

**Sobre la regla propuesta ("Zona" en vez de "Área"):** de acuerdo, y no es un cambio nuevo — es alinear la UI con el nombre que el contrato ya usa. Del lado backend "Área" solo aparece en `GET /plantas/{id}/areas` (estadísticas por zona, `AreaEstadisticasDTO`), que se renombra cuando ISA-95 tenga fecha. El selector de tres niveles queda entonces: **Planta** (`/auth/me → plantas[]`) › **Zona** (`/layout → zonas[]`) › **TGBT** (`/unifilar → nodos[].tipo == "tgbt"`), unidos por `device_id`.

## 7. Addendum (mismo día): endpoints eliminados y cambio en `PATCH`

Después de este informe hicimos el saneamiento YAML ↔ MySQL (cuatro commits, `refactor(estructura)`, `refactor(suscripcion)`, `refactor(grupos)`, `feat(instalacion)`). Lo que les toca:

| Cambio | Efecto en el frontend |
|---|---|
| `POST /api/v1/organizaciones`, `POST /api/v1/plantas`, `PUT /api/v1/plantas/{id}/unifilar`, `PUT /api/v1/plantas/{id}/layout` **eliminados** | Respondían 200 sin persistir nada (repositorio YAML de solo lectura). Ahora `405`. La estructura de planta se edita por commit al YAML del backend. Si tenían pantallas de edición de unifilar/layout, hoy no hacían nada real. |
| `/api/v1/grupos-dispositivos*` **eliminado** | Duplicaba al nodo virtual del unifilar (`GET …/unifilar/nodos/{id}/resumen` e `/historico`). No figuraba en la guía; en producción estaba vacío. |
| `PATCH /api/v1/dispositivos/{id}` puede responder **`422 {"detail": "Gestionado por YAML: …"}`** | Solo para `ubicacion_tag`, `tipo_instalacion`, `fases_con_ti`, `categoria_tarifaria`, `penalizacion_reactiva_aplica` y solo cuando el YAML los declara para ese medidor. **Hoy no hay ninguno declarado**: comportamiento idéntico. Avisaremos antes de cargar el primero. |
| `GET /organizaciones` | Misma forma. `plan_id`, `pro_vence_en` y `modo_free` ahora salen de MySQL (suscripción) en vez del YAML. |

## 8. Checklist para el frontend

- [ ] Ampliar el schema de `NodoUnifilarDTO`: `tipo` como enum cerrado, `nombre_maquina: string | null`.
- [ ] Dejar de asumir que el medidor está en el nodo `transformador` — buscar `tipo == "tgbt"` (o, más robusto, `es_virtual == false`).
- [ ] `MeResponseDTO`: `plantas[]` y `planta_activa_id`. Selector de Planta alimentado solo desde ahí (no desde `GET /plantas`), bloqueado cuando la activa tiene `puede_cambiar: false`.
- [ ] Nivel intermedio del selector rotulado **"Zona"**, desde `GET /layout → zonas[]`, no desde el unifilar.
- [ ] Pantalla de admin (opcional) contra `PUT /usuarios/{id}/plantas`.
