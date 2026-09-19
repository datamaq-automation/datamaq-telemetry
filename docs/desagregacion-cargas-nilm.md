# Desagregación de Cargas (NILM) sobre un Medidor Agregado

> **Estado:** Implementado (fases 0-3). Contexto `src/domain/cargas/`.
> **Origen:** Extensión del paso 4 del roadmap de [`docs/disponibilidad-maquina-diseno-conceptual.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/disponibilidad-maquina-diseno-conceptual.md) §8, que dejó fuera de alcance el modelo de datos de la desagregación.
> **Banco de pruebas:** medidor domiciliario monofásico (1P2W) midiendo la casa entera. El modelo es genérico (`Carga`) para aplicarse igual a un tablero industrial.

---

## 1. El problema

Un medidor agregado ve la suma de todas las cargas conectadas detrás de él. Con *n* cargas independientes hay hasta 2ⁿ combinaciones de encendido posibles, y el histograma bimodal que alcanza para una máquina sola (§5 del doc conceptual) deja de servir. Es el problema clásico de **NILM** (*Non-Intrusive Load Monitoring*, Hart 1992).

La plataforma aporta dos ventajas que no son obvias:

* **Ya persiste potencia reactiva.** `total_reactive_power` estaba en la base sin que ningún análisis lo usara. El par (ΔP, ΔQ) es el espacio de firmas de Hart y separa gratis una resistencia (Q≈0, FP≈1) de un motor (Q alta, FP 0.5-0.8).
* **Ya sabe poner el medidor en ráfaga.** `realtime_sync_mode` existe y `_ws_heartbeat_loop` lo renueva cada 60 s cuando hay un navegador conectado. Ese caudal de 1-5 s llegaba al servidor y **se descartaba**, porque la ingesta solo persiste una lectura cada 300 s.

---

## 2. Qué se puede afirmar a 5 minutos de cadencia

La cadencia permanente se mantiene en 300 s por decisión de diseño. Eso fija un techo duro: un evento de duración *d* tiene probabilidad `min(1, d/300)` de contener siquiera una muestra. **Ningún algoritmo puede recuperar una muestra que el hardware no tomó.**

| Aparato | P típica | Duración ON | A 5 min | Por qué |
|---|---|---|---|---|
| Heladera | 90-150 W (motor) | 15-30 min, cíclico | **Detectable** | 3-6 muestras por ciclo |
| Freezer | 100-200 W (motor) | 20-40 min, cíclico | **Detectable** | Se confunde con la heladera si sus ΔP no se separan más que su MAD |
| Termotanque | 1000-2000 W | 20-60 min | **Detectable** | Escalón grande y largo |
| Lavarropas | 2000 W → 150-500 W | 60-90 min | **Detectable** | Perfil secuencial distintivo (calienta alto, después motor con Q) |
| Horno eléctrico | 1500-2500 W | 30-90 min | **Detectable** | Se separa del termotanque por duración |
| Anafe eléctrico | 1000-2000 W | 5-30 min | **Marginal** | 1-6 muestras, baja confianza |
| Pava eléctrica | 1500-2200 W | 2-4 min | **No detectable por evento** | ~60% de chance de *una* muestra, indistinguible de un arranque |
| Iluminación | 20-200 W (LED) | horas | **No separable como escalón** | Por debajo del ruido de la línea base |

El motor entrega **atribución de consumo con residual explícito**, no NILM por eventos completo. Pava e iluminación caen en `NO_ATRIBUIDO` por diseño. Ese residual es una salida de primera clase: un balance que siempre cierra no informa nada.

`GET /api/v1/cargas/perfil` devuelve siempre `advertencia_cadencia` para que el consumidor pueda distinguir **"no hubo"** de **"no se pudo ver"**.

---

## 3. Arquitectura

```
src/domain/cargas/
├── entities.py        Carga · CampanaCaracterizacion · IntervaloActividadCarga
├── value_objects.py   FirmaCarga · EscalonPotencia · EpisodioCarga · CicloOperacion
│                      EstadisticaCiclos · PerfilLineaBase · AtribucionConsumo · enums
├── ports.py           RepositorioCargasPort · RepositorioCampanasPort
│                      RepositorioIntervalosActividadPort · RepositorioSeriePotenciaPort
│                      ComandoRafagaPort
├── exceptions.py
└── servicios/
    ├── estadistica.py            mediana · MAD · percentil · cadencia (robustos, stdlib)
    ├── perfilador_linea_base.py  consumo permanente vs. consumo de actividad
    ├── analizador_ciclos.py      duración ON/OFF · duty cycle · PatronOperacion
    ├── detector_escalones.py     ΔP/ΔQ · emparejado en episodios
    ├── emparejador_firmas.py     puntaje de 4 factores · decisión o abstención
    ├── calibrador_firma.py       campaña → FirmaCarga · detección de contaminación
    └── atribuidor_consumo.py     reparto de kWh · residual
```

Dominio stdlib puro, sin numpy ni scipy (`CONVENTIONS.md` §3). Reusa `SegmentadorRegimenesService` de `disponibilidad` para la partición modal en vez de reimplementarla.

### Servicios clave

**`PerfiladorLineaBaseService`** — el único análisis que da un resultado sólido a 300 s sin ninguna firma calibrada. Percentil 10 por ventana horaria (no el mínimo, que lo fija una sola lectura espuria), franja 02-04 local para la base nocturna. `delta_diurno_W` **no es "iluminación"**: es todo lo que se suma de día y no se puede separar en escalones. Se reporta sin bautizarlo.

**`AnalizadorCiclosService`** — responde el pedido de "período de funcionamiento y de inactividad": mediana y MAD de duración ON y OFF, duty cycle, período, y de ahí infiere `PatronOperacion`. Devuelve `INDETERMINADO` cuando no alcanza la evidencia. Soporta histéresis para que una carga que roza el umbral no se fragmente hasta desaparecer.

**`EmparejadorFirmasService`** — puntaje **multiplicativo** de cuatro factores en [0,1], no promedio: un promedio deja que un factor excelente compense a uno que dice "esto no puede ser".

1. Potencia, tolerada por la dispersión medida.
2. Reactiva — separa familias enteras (motor vs. resistivo).
3. **Duración** — el único factor que separa entre sí a pava, anafe, termotanque y horno, que son indistinguibles por ΔP y ΔQ.
4. Horario — desempate débil (todavía neutro; falta declarar franjas por carga).

Se abstiene (`NO_ATRIBUIDO`) si el mejor candidato no llega a 0.35, o si no supera al segundo por un factor de 1.5.

**`DetectorEscalonesService`** — umbral calibrado del ruido de la propia serie (MAD de los ΔP), con respaldo por percentil solo cuando la MAD degenera a cero. Dos guardas físicas: se descarta un episodio de más de 6 h (es un apagado perdido, no una carga) y uno de potencia media negativa (una carga no consume potencia negativa).

---

## 4. Campañas de caracterización

Resuelven por **instrumentación** lo que la matemática no puede: ponen el medidor en ráfaga durante una ventana acotada y guardan todo, sin tocar la cadencia permanente ni el downsampling de 300 s.

| Tipo | Para qué | Cómo |
|---|---|---|
| `ACTIVA` | Lo que se prende a voluntad: pava, anafe, horno, lavarropas, iluminación | Se abre la campaña, se esperan ~60 s (pre-roll que mide la línea de base), se prende el aparato |
| `PASIVA` | Lo que cicla solo: heladera, freezer, termotanque | Se apaga el resto de la casa y se observan varias horas, dejando que el termostato haga su ciclo |

Duraciones sugeridas: pava 5 min · anafe/horno 20 min · lavarropas ciclo completo 90 min · iluminación 10 min de noche · heladera/freezer/termotanque 3-4 h pasiva. **Para separar heladera de freezer**, campaña pasiva con uno de los dos desenchufado: el freezer aguanta 4 h sin problema.

Toda la medición es **diferencial contra la línea de base**: sin restar el fondo, la firma de la pava incluiría a la heladera.

**Contaminación.** Si durante la ventana entra otra carga, la campaña se cierra como `CONTAMINADA` y **no produce firma**. Dos síntomas independientes: la potencia se movió más de un 25% en régimen (`DISPERSION_EXCESIVA`), o hubo un escalón neto de más de 100 W en el medio (`ESCALON_AJENO` — atrapa el caso que el primero no ve: una carga que entra y se queda desplaza la mediana sin dispersarla). No se emite una firma sucia con una advertencia al lado, porque la advertencia se pierde y la firma se usa igual durante meses.

**Sostenimiento.** `time_s` de `realtime_sync_mode` es una **duración**, no un período: `_loop_campanas_activas()` (`server.py`) la renueva cada 45 s y cierra las campañas vencidas, independiente de si hay clientes WebSocket. Sin eso una campaña de madrugada volvería a 5 minutos en medio de la medición, y una campaña olvidada dejaría al medidor publicando indefinidamente.

---

## 5. Modelo de datos

Tablas nuevas en `src/infrastructure/sqlalchemy/models_cargas.py` (módulo aparte de `models.py` para no empujarlo contra el límite de 500 líneas; `alembic/env.py` lo importa explícitamente).

| Tabla | Rol | Claves |
|---|---|---|
| `loads` | Catálogo de cargas con su firma vigente embebida | `UNIQUE (device_id, name)` — un medidor ve N cargas, a diferencia de `machines` que es 1:1 |
| `characterization_campaigns` | Ventanas de medición | `INDEX (device_id, state)` |
| `campaign_samples` | Lecturas de alta resolución | `UNIQUE (campaign_id, recorded_at)` — idempotencia ante el redelivery de MQTT QoS 1 |
| `load_activity_intervals` | Intervalos atribuidos; `load_id` nulo = `NO_ATRIBUIDO` | `UNIQUE (device_id, start_at, end_at)` — idempotencia del batch |

Migraciones: `e2f3a4b5c6d7` → `f3a4b5c6d7e8` → `a4b5c6d7e8f9`.

`campaign_samples` es tabla propia y no `telemetry_instantaneous` por tres razones: no debe romper el supuesto de granularidad uniforme de `ConsultarTelemetriaUseCase`, no debe caer en la purga por retención (es verdad de terreno, el activo del proyecto), y su vida está atada a la campaña.

**Volumen.** A 1 s son 3600 filas/hora: una campaña activa típica deja 600-5400 filas y una pasiva de 4 h, 14.400. Caracterizar los 8 aparatos ≈ 50-80k filas, una sola vez. No se purgan.

> **Regla dura:** el batch **nunca** pisa una fila con `origin = 'CORRECCION_HUMANA'`. Esas filas son el dataset etiquetado que la §7 del doc conceptual dice que hace falta para cualquier modelo futuro, y es lo único que ninguna regla puede regenerar.

---

## 6. Captura durante la campaña

`CapturadorCampanaIngesta` es un **sumidero paralelo** inyectado como dependencia opcional de `IngestarTelemetriaUseCase`, igual que `disponibilidad_use_case`. No toca el downsampling de 300 s ni escribe en `telemetry_instantaneous`: la serie permanente es idéntica con campaña o sin ella.

`RegistroCampanasActivas` vive en memoria porque se consulta **una vez por cada lectura MQTT entrante**, a caudal de ráfaga. Un SELECT por lectura pondría la base en el camino crítico para responder casi siempre que no hay campaña.

> **Dependencia de despliegue:** el registro asume que la API y el listener MQTT **comparten proceso** (el listener corre en el lifespan de FastAPI) y que hay **un solo worker de uvicorn** (`systemd/datamaq-api.service`). Si eso cambia, el registro deja de ver las campañas que abre la API y hay que moverlo a la base. La fuente de verdad sigue siendo la tabla: `_loop_campanas_activas()` rehidrata el registro al arrancar desde las campañas `EN_CURSO`.

Un fallo capturando nunca interrumpe la ingesta: perder una muestra de campaña se resuelve repitiéndola; perder la telemetría permanente, no.

---

## 7. Motor batch

`AtribuirConsumoUseCase` corre diferido, no en la ingesta. La duración de un encendido es la mitad de su identidad y en vivo no se conoce hasta que el evento terminó; sobre una ventana cerrada además se puede reprocesar cuando alguien corrige una etiqueta.

* `scripts/analizar_consumo.py` + `systemd/datamaq-analisis.{service,timer}` (horario), mismo patrón que la purga.
* `POST /api/v1/cargas/analisis` para dispararlo a demanda.
* **Idempotente:** re-correr la misma ventana reescribe sus intervalos en vez de duplicarlos.

El total del período sale del **contador acumulado** (`telemetry_energy`), que es exacto. No se integra la serie instantánea de 5 minutos: entre muestra y muestra puede haber prendido y apagado cualquier cosa, y esa integral sería sistemáticamente sesgada.

**Sobre-conteo.** Con cargas anidadas el episodio externo incluye la potencia de la interna, así que lo atribuido puede superar al consumo real. El servicio lo **denuncia** en vez de repartir la diferencia: *"Hay cargas contándose dos veces: revisá firmas con potencias solapadas."*

---

## 8. API — `/api/v1/cargas`

Recurso nuevo y aditivo. **No modifica ningún DTO de telemetría existente.**

| Método | Ruta | Qué hace |
|---|---|---|
| `GET`/`POST` | `/` | Catálogo de cargas |
| `PATCH` | `/{carga_id}` | Editar carga |
| `PUT` | `/{carga_id}/firma` | Fijar firma manual (calibración sin campaña) |
| `GET` | `/perfil?device_id&dias&zona` | Línea base, ciclado y regímenes — **funciona sin ninguna firma** |
| `POST` | `/campanas/activas` · `/campanas/pasivas` | Abrir campaña |
| `GET` | `/campanas/{id}` | Estado y firma resultante |
| `PATCH` | `/campanas/{id}/finalizar` · `/descartar` | Cerrar campaña |
| `GET` | `/{carga_id}/campanas` | Historial de campañas de una carga |
| `POST` | `/analisis?device_id&dias` | Disparar el batch |
| `GET` | `/atribucion?device_id&dias` | kWh por carga + residual |
| `GET` | `/{carga_id}/intervalos` | Intervalos de actividad |
| `PATCH` | `/intervalos/{id}/corregir` | Corrección humana (feedback loop) |

Las rutas fijas (`/perfil`, `/atribucion`, `/analisis`, `/intervalos/...`, `/campanas/...`) se declaran **antes** que `/{carga_id}`, si no FastAPI las leería como ids de carga.

---

## 9. Orden de trabajo recomendado

1. **Cargar el catálogo** con los aparatos y su potencia de chapa. Es el conocimiento del proceso que la §6.3 del doc conceptual dice que hay que *inyectar*, no esperar que la estadística lo descubra.
2. **`GET /perfil`** sobre 14 días. Da línea base, ciclado y consumo de fondo sin ninguna campaña. Es el primer resultado real.
3. **Campañas**, una por aparato. Empezar por los que más pesan (termotanque, horno, lavarropas) y por los cíclicos de madrugada.
4. **`POST /analisis`** y **`GET /atribucion`**. Contrastar el total contra `GET /api/v1/telemetria/energy?granularity=day`.
5. **Corregir a mano** lo que esté mal. Eso construye el dataset etiquetado.

---

## 10. Límites conocidos y trabajo pendiente

* El factor horario del emparejador es neutro: falta declarar franjas típicas por carga.
* Heladera y freezer se separan solo si sus ΔP difieren más que su MAD; si no, corresponde tratarlos como grupo `REFRIGERACION`.
* El sobre-conteo por anidamiento se detecta pero no se corrige. Corregirlo requiere un modelo de estados conjunto (HSMM, §5.5 del doc conceptual).
* Pava e iluminación no son atribuibles por evento a esta cadencia. Se podrían estimar estadísticamente por franja horaria.
* El tópico `/harmonics` del medidor trae 25 armónicos de V e I por fase y **viene deshabilitado de fábrica**. Sería un discriminador NILM fuerte (separa electrónica de resistivo de motor mejor que Q sola).
* **Maquinaria Industrial y Variables de Proceso [Resuelto en Dominio, 2026-09-19]:** Se implementó `ModeloMotorFisicoService` y `CatalogoPresetsIndustriales` para física electromecánica ($LF = P/P_{nom}$, reactiva de magnetización) y `DesagregadorAsistidoService` en conjunto con el dominio `produccion` (`CalculadorEnPIService`, SEC en kWh/m y kWh/corte) para desambiguar TGBT con sensores inductivos.
* **Techo Determinístico en TGBT y Transición a ML (ISO 50006) [Decisión 2026-09-19]:** Se formalizó el agotamiento de la clasificación por reglas sobre medidores agregados en TGBT (`decisions/2026-09-19_clasificacion-energia-industrial-enpi-ml.md`). La descomposición de cargas no instrumentadas y la detección de anomalías se delegarán a modelos de regresión multivariable y análisis de residuos en `datamaq-hub`.

