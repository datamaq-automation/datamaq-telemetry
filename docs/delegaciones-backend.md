# Backlog de Delegaciones y Mejoras Técnicas al Backend (`datamaq-telemetry`)

> **Documento:** `docs/delegaciones-backend.md`  
> **Estado:** Backlog Consolidado de Solicitudes  
> **Destinatario:** Equipo de Backend & Datos (`datamaq-telemetry`)  
> **Fecha:** 2026-08-23  
> **Autor:** DataMaq — Dirección de Ingeniería y Arquitectura

---

## 1. Módulo de Autenticación y Seguridad

| ID       | Solicitud                                 | Justificación UI/UX                                                                                                                                          | Estado                                                                    |
| :------- | :---------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| **D-01** | `GET /api/auth/me`                        | Retornar `{ "usuario": str, "rol": str }` desde los claims del JWT para restaurar la sesión tras un refresh (`F5`) sin depender de sondeos indirectos.       | ✅ Soportado en Frontend e integrado con fallback `username`/`usuario`    |
| **D-02** | Header `Retry-After` en `429`             | Informar con exactitud los segundos de espera en la interfaz de usuario ante bloqueos por fuerza bruta o rate limit.                                         | ✅ Desplegado en Backend e integrado en `useLogin.ts`                     |
| **D-03** | `request_id` en Errores `≥ 500`           | Adjuntar `X-Request-ID` para correlación inmediata de trazas en el log de FastAPI.                                                                           | ⏳ Pendiente en Backend                                                   |
| **D-04** | `POST /api/auth/guest`                    | Permitir acceso instantáneo con rol `invitado` sin enviar credenciales desde el cliente (respetando la regla de cero secretos).                              | ⏳ Pendiente en Backend                                                   |
| **D-05** | `POST /api/usuarios`                      | Alta de operadores y técnicos administrada por rol `admin`.                                                                                                  | ⏳ Pendiente en Backend                                                   |
| **D-07** | `GET /api/v1/sge/documentacion?rol={rol}` | Retornar catálogo de guías y procedimientos del SGE (ISO 50001) y flag `sgen_activo: bool` según la planta del usuario con fallback local resiliente en SPA. | ✅ Desplegado en Backend e integrado en SPA con fallback local resiliente |

---

## 2. Configuración y Metrología de Dispositivos

### `PATCH /api/dispositivos/{device_id}`

Permitir la actualización parcial de parámetros metrológicos desde la interfaz:

```json
{
  "nombre": "Inyectoras 1 a 4",
  "ubicacion_tag": "Nave 2 · TGBT-02",
  "numero_serie": "SN-98234-DM",
  "tipo_instalacion": "3P4W",
  "fases_con_ti": "S,T"
}
```

---

## 3. Granularidad Temporal en Históricos de Potencia y Energía

### `GET /api/telemetria/instantaneous/{device_id}`

Soportar el parámetro `granularity` (`auto`, `1m`, `5m`, `15m`, `1h`) para optimizar el tamaño de los payloads transferidos:

- **Ventana de 2h:** `granularity=1m` ($\approx 120$ puntos) — Diagnóstico de transitorios de arranque.
- **Ventana de 24h:** `granularity=5m` ($\approx 288$ puntos) — Balance diario.
- **Ventana de 7d:** `granularity=15m` ($\approx 672$ puntos) — Integración estándar para control tarifario ENRE/CAMMESA.

---

## 4. Ingesta de Distorsión Armónica Total (THD)

### Ingesta MQTT `m/wifi/{mac}/inst`

Incorporar en la ingesta y modelo de base de datos las magnitudes de distorsión armónica:

- `thd_v_r`, `thd_v_s`, `thd_v_t` (Distorsión de tensión; umbrales internos de alerta, no normativos).
- `thd_i_r`, `thd_i_s`, `thd_i_t` (Distorsión de corriente).
- Disparo automático de alerta `RIESGO_RESONANCIA_CAPACITORES` cuando $\text{THD}_V > 4.0\%$ simultáneo con $\text{FP} > 0.98$.

---

## 5. Topología Unifilar y Layout Espacial Dinámico

### `GET /api/v1/planta/unifilar` y `GET /api/v1/planta/layout`

Para futuras fases donde las empresas configuren su propia red eléctrica personalizada desde la base de datos:

- Retornar la lista de nodos con relación de parentesco (`parent_id`), tipo (`acometida`, `transformador`, `tgbt`, `seccional`, `carga`) y `device_id` asociado.
- Retornar coordenadas vectoriales (, Y$) para posicionamiento de celdas en el plano de planta.

---

## 6. Analítica de Reactiva: alcance tarifario y estabilidad del veredicto

> **Origen:** el banner «Alerta de Penalización por Energía Reactiva» del dashboard aparecía y
> desaparecía varias veces por minuto, y se mostraba también en circuitos monofásicos
> residenciales, donde el cargo por reactiva no existe.
>
> **Ya mitigado en la SPA (v1.8.x):** histéresis de presentación
> (`features/telemetria/dominio/penalizacionReactiva.ts`) y conservación del bloque `analitica`
> cuando el WS no lo transporta. Son paliativos de render: **no** corrigen el veredicto, que por
> la regla Thin Client (§ `AGENTS.md`) es potestad exclusiva del backend.

| ID       | Solicitud                                     | Justificación                                                                                                                 | Prioridad     |
| :------- | :-------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- | :------------ |
| **D-11** | Alcance tarifario del régimen de penalización | La penalización no aplica a todos los usuarios: la SPA la muestra hoy en circuitos donde no existe el cargo.                  | 🔴 Bloqueante |
| **D-12** | Veredicto sostenido sobre ventana integrada   | `requiere_compensacion` se emite por muestra; la penalización se factura sobre la relación mensual $\text{kVArh}/\text{kWh}$. | 🔴 Alta       |
| **D-13** | `analitica` siempre presente en el WS `inst`  | Los mensajes que caen por el normalizador legacy llegan sin el bloque y apagaban la alerta en la SPA.                         | 🟠 Media      |
| **D-14** | Umbral de abstención de 500 W sobre ventana   | El corte por muestra alterna entre nulo y no nulo en cargas intermitentes.                                                    | 🟠 Media      |
| **D-15** | Penalización como alerta persistida           | Un banner recalculado en cada render no deja historial ni acuse de resolución.                                                | 🟢 Opcional   |

### D-11 · Alcance tarifario (raíz del falso positivo en monofásico residencial)

La Resolución ENRE N° 184/2000 rige el recargo por bajo factor de potencia para usuarios con
demanda **> 10 kW** (categorías T2 / T3). Una **T1-R monofásica residencial no paga cargo por
reactiva**, de modo que emitir `requiere_compensacion: true` y un monto en pesos para esos
dispositivos es un veredicto incorrecto, no un problema de presentación.

Se solicita:

1. Incorporar al modelo de dispositivo la categoría tarifaria — `categoria_tarifaria`
   (`T1-R | T1-G | T2 | T3`) o, como mínimo, el booleano derivado
   `penalizacion_reactiva_aplica` — expuesta en `GET /api/dispositivos` y editable vía
   `PATCH /api/dispositivos/{id}`, junto a `tipo_instalacion` y `fases_con_ti` (§2).
2. Que el motor de analítica emita `requiere_compensacion: false` y
   `penalizacion_estimada_ars: null` cuando la categoría no está alcanzada por el régimen.
3. Deseable: `motivo_exclusion: "TARIFA_SIN_CARGO_REACTIVA"` en `AnaliticaCalidadEnergiaDTO`,
   para que la SPA pueda explicar la ausencia de veredicto en lugar de callar.

> El dimensionamiento del banco de capacitores (`banco_sugerido_kvar`) **sigue siendo válido** en
> estos casos como recomendación técnica: lo que no corresponde es la cuantificación financiera.

### D-12 · Veredicto sostenido, no instantáneo

`requiere_compensacion` y `penalizacion_estimada_ars` deberían calcularse sobre ventana integrada
(intervalo de 15 min de ENRE, o acumulado del ciclo de facturación) con banda de histéresis, en
vez de sobre una muestra de 1 s. Se solicita además transportar en el DTO:

- `ventana_evaluacion_min` (entero): sobre qué ventana se emitió el veredicto.
- `vigente_desde` (ISO-8601 con `Z`): desde cuándo la condición se sostiene.

Con esto, la histéresis de la SPA pasa a ser una red de seguridad y no el mecanismo principal, y
el dashboard puede informar «penalizado desde las 14:35» en lugar de un estado sin historia.

### D-13 · `analitica` siempre presente en el subtópico `inst`

El WS debe emitir el mismo DTO que REST **incluyendo** el bloque `analitica` (con `null` en los
campos de los que se abstiene) en vez de omitir la clave. Hoy, cuando un mensaje cae por la vía de
fallback (`normalizarLecturaInstantanea`), la lectura llega sin el bloque y la SPA se quedaba sin
veredicto hasta la siguiente respuesta REST.

### D-14 · Umbral de abstención por potencia evaluado sobre ventana

El corte de `P < 500 W` documentado en `contratos-api.md` §3.1.1 se evalúa por muestra. En cargas
intermitentes eso alterna entre valor y `null` entre lecturas consecutivas: debería aplicarse
sobre el promedio de la ventana de D-12.

### D-15 · (Opcional) Emitir la penalización como alerta persistida

`tipo_alerta: "PENALIZACION_REACTIVA"` con severidad, `iniciado_en` y `resuelto_en`, para que la
condición viva en `AlertsPanel` con historial y acuse de resolución, en lugar de un banner
efímero recalculado en cada render.
