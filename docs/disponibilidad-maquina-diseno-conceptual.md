# Disponibilidad de Máquina a partir del Comportamiento Energético — Diseño Conceptual

> **Estado:** Documento de diseño conceptual. No describe código existente ni un plan de implementación con tablas/servicios definidos — es la base de razonamiento para una futura sesión de diseño técnico.
> **Origen:** Sesión de diseño 2026-09-02/03, orientada a evaluar cómo derivar disponibilidad de máquina (marcha / parada programada / parada no programada) a partir de las variables eléctricas que ya captura la plataforma.

---

## 1. Objetivo y alcance

Datamaq Telemetry mide hoy variables eléctricas por medidor (potencia, corriente, tensión, energía acumulada) y evalúa calidad de energía. El objetivo de este documento es sentar las bases conceptuales para, a partir de ese comportamiento energético, **inferir indirectamente la disponibilidad de las máquinas**: tiempo en marcha, tiempo de parada programada y tiempo de parada no programada.

Este documento **no define** todavía tablas, servicios ni endpoints — es intencionalmente conceptual, para alinear criterio antes de comprometer un diseño técnico.

---

## 2. Punto de partida: qué existe en la plataforma

Relevado sobre el modelo de datos y el código de dominio (`src/domain/disponibilidad/entities.py`, `src/infrastructure/sqlalchemy/models.py`):

- **`Maquina`**: Entidad de dominio vinculada 1:1 a un `Dispositivo` (ej: SmartPlus), con umbral de marcha calibrable (`on_threshold_w`) y filtros de persistencia temporal (`persistence_readings`, `persistence_seconds`).
- **`EventoDisponibilidad`**: Registro de intervalos de disponibilidad con estado (`MARCHA`, `PARADA`), tipo de parada (`PROGRAMADA`, `NO_PROGRAMADA`), potencia promedio y origen de clasificación (`REGLA`, `MANUAL`, `AUTOMATA`).
- **`ParadaProgramada`**: Calendario de paradas planificadas (mantenimiento, turnos) vinculable a cada máquina por intervalo de tiempo.
- **`telemetry_instantaneous`**: Potencia activa/reactiva/aparente, corriente y tensión por fase y totales cada 5 minutos (o 1-5s en modo ráfaga `realtime_sync_mode`).
- **Arquitectura Híbrida (Energía + PLC Automate 24V-4M)**: Coexisten en la misma máquina el medidor Smart Plus (dimensión energética) y el PLC Automate (dimensión de maniobra/control vía E/S discretas por Ethernet).

---

## 3. Certezas

1. **La disponibilidad es un estado de 3 valores:** marcha / parada programada / parada no programada. La señal eléctrica se cruza con las `ParadaProgramada` cargadas en el sistema para determinar si la parada fue planificada.
2. **Fusión Sensorial (Smart Plus + Automate 24V-4M):** La combinación de la potencia activa $P(t)$ (Smart Plus) con las entradas digitales discretas (Automate 24V-4M) elimina la ambigüedad en paradas, permitiendo asignar automáticamente el `origen: AUTOMATA` y la causa raíz exacta cuando se activa un contacto de falla o paro de emergencia.
3. **Un enfoque por reglas (umbrales de potencia) es el punto de partida correcto**, no un atajo inferior al aprendizaje automático. Es interpretable, auditable, no requiere datos históricos etiquetados, y es el estándar de la industria (OEE/TPM) antes de cualquier capa de ML.
4. **El ML supervisado necesita "verdad de terreno" (ground truth) para entrenar, y hoy no existe.** Las reglas y las señales del PLC son la forma de generar las primeras etiquetas (con ruido controlado) para arrancar un dataset histórico.
5. **La cadencia real de datos (5 min estándar) define el piso de resolución temporal.** Un micro-paro de 30 segundos no se puede detectar como evento propio salvo activar el modo ráfaga para esa máquina puntual.
6. **El umbral marcha/parada se puede calibrar empíricamente**, a partir del histograma de potencia de cada máquina (`/api/v1/disponibilidad/maquinas/{id}/histograma`).
7. **Cuando un medidor mide exclusivamente una máquina (submedición pura)**, no hay problemas de desagregación de cargas (NILM); el 100% de la señal $P(t)$ corresponde al proceso activo de esa máquina.

---

## 4. Dudas abiertas (a relevar antes de comprometer diseño técnico)

| # | Duda | Por qué importa |
|---|---|---|
| 1 | ¿Umbral de marcha/parada por % de potencia nominal o calibrado empíricamente por máquina? | Define si hace falta modelar potencia nominal por máquina o alcanza con datos históricos de consumo. |
| 2 | ¿Las máquinas tienen consumo de standby no nulo (auxiliares, control, calefacción)? | El umbral no puede fijarse "cerca de cero" si existe consumo de standby relevante. |
| 3 | ¿El calendario externo de paradas programadas tiene API/export, o es carga manual? | Determina si el cruce programada/no-programada puede automatizarse. |
| 4 | Para medidores que agregan varias máquinas, ¿alcanza con disponibilidad "de línea" en una primera etapa, o se necesita granularidad por máquina desde el día uno? | Si se necesita por máquina, hay que evaluar desagregación algorítmica vs. submedición dedicada (sección 6.4). |
| 5 | ¿Quién correge una clasificación errónea (operario, supervisor)? | Ese mecanismo humano es, a la vez, la fuente de etiquetas para el futuro modelo de ML. |
| 6 | ¿Sobre qué ventana temporal se calibra el histograma de cada máquina, y con qué periodicidad se recalibra? | Una ventana corta puede no cubrir ambos estados (marcha/parada); el consumo operativo puede correrse con el desgaste del equipo. |
| 7 | Para medidores agregados: ¿las cargas individuales tienen consumos de potencia suficientemente distintos entre sí, y no suelen prenderse/apagarse simultáneamente? | Condiciona si la desagregación por clustering o por eventos es viable (sección 6.2). |
| 8 | ¿La potencia de una línea de producción es estable en operación o varía según producto/velocidad? | Si varía, tanto el clustering por nivel como la firma de escalón pierden confiabilidad. |

---

## 5. Segmentación modal de regímenes de potencia

### 5.1 De la calibración bimodal a la partición modal general (k modas)

Para una máquina que alterna entre parada y marcha, el histograma de sus lecturas de potencia (eje X = potencia, eje Y = frecuencia de lecturas) tiende a ser bimodal: una campana angosta cerca del consumo de parada/standby, y otra más ancha centrada en la potencia operativa típica. El **valle** entre ambas campanas es el umbral que minimiza la clasificación errónea — análogo al método clásico de Otsu en procesamiento de imágenes.

Sin embargo, fijar el problema a $k=2$ presenta tres límites severos:
1. **El ancho de bin lo fija el outlier:** un arranque de motor (6–8× la nominal) estira el rango crudo y colapsa la campana de standby en un solo bin, destruyendo el valle.
2. **Heterocedasticidad:** un standby angosto (decenas de W) y una marcha ancha (kW) tienen dispersiones incompatibles con un ancho de bin uniforme.
3. **Máquinas multiproceso y medidores agregados (NILM):** exhiben múltiples regímenes estables ($k > 2$).

Por ende, el umbral de marcha/parada se modela formalmente como el **caso particular $k=2$** de un servicio general de **segmentación modal**: identificar las potencias típicas (**modas**, regímenes estables) y las potencias de transición (**antimodas**, valles) que delimitan una **partición modal** del eje de potencia.

### 5.2 Escala logarítmica: visualización vs. estimación

Es crítico distinguir dos usos de la escala logarítmica que responden a necesidades distintas:

* **Log en el eje de potencia (estimación / resolución de bins):** es una decisión de modelado físico. El ruido de potencia en régimen escala con la potencia ($\Delta P \propto P$). Construir bins de ancho constante en $\log(P + \epsilon)$ genera **bins de ancho relativo constante en watts** (ej. 10 W cerca de 100 W, 1 kW cerca de 10 kW). Un solo parámetro de binning resuelve standby y marcha sin sobre-suavizar uno ni sub-suavizar el otro, y evita que un transitorio estire el rango dinámico lineal. $\epsilon$ aproxima el cuanto de resolución del ADC/firmware.
* **Log en el eje de frecuencia (ayuda visual para presentación):** si la máquina opera 85% del tiempo en parada y 15% en marcha, la campana de marcha se aplana contra el eje X en escala lineal. La escala log en el conteo comprime la campana dominante para hacer visible la minoritaria en UI.

Ambas técnicas son válidas y complementarias, pero operan sobre ejes distintos.

### 5.3 Persistencia topológica 1-D y validación por barrido de ancho de banda

Para identificar modas significativas sin fijar un umbral de prominencia empírico arbitrario:

1. **Persistencia topológica 1-D (Merge Tree por Union-Find):** se ordenan las alturas suavizadas de forma descendente. Al barrer, los máximos locales nacen como componentes conexas independientes; cuando dos componentes se tocan en un valle, la componente más baja (más joven) muere absorbida por la más alta. Su *persistencia* es la caída de densidad necesaria para alcanzar un pico mayor. Esto rankea rigurosamente la saliencia de cada régimen y descarta fluctuaciones espurias en $O(n \log n)$ con stdlib puro.
2. **Barrido de ancho de banda (ancho crítico de Silverman discreto):** el número de modas es monótono no creciente con el radio de suavizado. Barriendo ventanas $[1, 3, 5, \dots, 15]$ y evaluando persistencia, la estructura modal que forma una **meseta estable** representa regímenes reales del proceso; picos que solo existen en ventanas angostas son ruido de muestreo. Esto provee una confianza continua $[0, 1]$ sobre la multimodalidad.

### 5.4 Dispersión robusta por régimen (MAD)

Una vez dividida la distribución por las antimodas:
* Mediana ($P_{50}$) y desviación absoluta respecto a la mediana (**MAD** — *Median Absolute Deviation*) se calculan directamente sobre las **lecturas crudas** asignadas a cada régimen, no sobre los bins discretizados, preservando la fidelidad metrológica.

### 5.5 Sucesores probabilísticos: GMM vs. HSMM

* **GMM (Gaussian Mixture Model):** es el sucesor estático natural para densidades continuas complejas, pero queda descartado en la capa de dominio por la directiva de arquitectura stdlib-only (`CONVENTIONS.md:19`).
* **HSMM (Hidden Semi-Markov Model):** es el modelo teórico definitivo para predecir comportamiento. La distribución marginal de potencia descarta el tiempo; un HSMM incorpora $k$ estados, distribución de potencia por estado, matriz de probabilidades de transición y distribución de tiempo de permanencia (duración). Es el estándar unificado de NILM y modelado de disponibilidad.

### 5.6 Dinámica temporal $|\Delta P| / \Delta t$ por régimen y la advertencia de cadencia

El histograma es una proyección marginal que no distingue dos causas de baja densidad:
1. **Regímenes transitorios:** la máquina pasa rápido por esa potencia.
2. **Regímenes estables infrecuentes:** la máquina opera establemente allí, pero con baja utilización.

Se separan midiendo la mediana de $|\Delta P| / \Delta t$ (W/s) entre muestras consecutivas, comparada contra el ancho de banda del propio régimen (para respetar la heterocedasticidad).

> [!WARNING]
> **La advertencia fundamental de cadencia de muestreo:**
> A cadencia estándar de 5 minutos ($300\text{ s}$), los valles del histograma **casi no contienen transiciones: contienen regímenes desocupados**. Una rampa de arranque que dura $20\text{ s}$ tiene una probabilidad de muestreo $\approx 20/300 \approx 6.6\%$ por evento; la potencia transitoria casi nunca es capturada. Ningún algoritmo matemático puede inventar muestras que el hardware no midió.
> 
> Caracterizar transiciones reales es un problema de **instrumentación**, no de algoritmo: requiere campañas acotadas con `realtime_sync_mode` ($1\text{--}5\text{ s}$) sobre máquinas de referencia para extraer firmas de transición. Por ello, ante cadencias inadecuadas o pares insuficientes, el dominio clasifica la naturaleza como `INDETERMINADO` en lugar de generar clasificaciones sin respaldo.

### 5.7 Estacionariedad del proceso

Una ventana histórica de 30 a 90 días puede fundir campanas si el proceso cambia (desgaste de herramental, variaciones de producto, cambio estacional).
El diagnóstico de estacionariedad divide la serie temporal en subventanas cronológicas iguales (ej. 4 tramos), segmenta cada una, y empareja modas consecutivas mediante vecino más cercano 1-D. Un desplazamiento relativo excesivo ($\Delta P / P > 20\%$) alerta al analista sobre deriva del proceso.

---

## 6. Medidores que agregan varias cargas: desagregación de cargas (NILM)

### 6.1 El problema

Ejemplo real de referencia: un medidor que agrega iluminación + compresor + línea de producción 1 + línea de producción 2. Con **n cargas independientes**, el número de combinaciones posibles de encendido/apagado es **2ⁿ** (con 4 cargas, hasta 16 estados teóricos) — el histograma bimodal de la sección 5 deja de alcanzar, porque ya no hay 2 estados sino potencialmente muchos.

Este es el problema clásico de **desagregación de cargas no intrusiva (NILM — Non-Intrusive Load Monitoring)**, estudiado desde los años 80 (Hart, 1992) para inferir qué electrodomésticos/cargas están activos a partir de un único medidor agregado.

### 6.2 Dos técnicas operativas en la plataforma

La implementación de `SegmentadorRegimenesService` convierte estas técnicas de aspiracionales a operativas:

* **Técnica A — Clustering por nivel de potencia:** implementada directamente mediante `SegmentadorRegimenesService.segmentar(k > 2)`. Identifica los niveles estables resultantes de combinaciones de cargas concurrentes mediante persistencia topológica sobre bins logarítmicos.
* **Técnica B — Detección de escalones ($\Delta P$):** implementada en `DetectorEscalonesService` (`src/domain/cargas/servicios/`), que replica el criterio de huecos del segmentador y agrega el emparejado de cada encendido con su apagado en episodios acotados. La atribución de cada episodio a una carga concreta vive en `EmparejadorFirmasService`, que usa el par $(\Delta P, \Delta Q)$ —la potencia reactiva ya estaba en la base— más la **duración**, que es el único eje que separa entre sí a cargas resistivas de potencia parecida.

Ambas se documentan en detalle en [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md).

### 6.3 El conocimiento del proceso reduce el espacio real de estados

El espacio combinatorio teórico (2ⁿ) casi nunca se da completo en la práctica: dependencias físicas del proceso (ej. "la línea no puede operar sin el compresor") eliminan combinaciones inválidas. Esa información debe **inyectarse como restricción de diseño**, no esperarse que la estadística la descubra sola — reduce el trabajo de calibración y mejora la confiabilidad de cualquiera de las dos técnicas.

### 6.4 Decisión de negocio: desagregación algorítmica vs. submedición dedicada

| | Desagregación algorítmica | Submedición dedicada (medidor por carga) |
|---|---|---|
| Costo | Sin hardware adicional | Costo de instalación y cableado |
| Confiabilidad | Frágil ante cargas de potencia variable, arranques simultáneos, o firmas que se degradan con el desgaste del equipo | Verdad directa, sin inferencia ni margen de error |
| Cuándo conviene | Cargas secundarias donde un error de clasificación no tiene consecuencia de negocio (ej. iluminación) | Cargas cuya disponibilidad individual es crítica para el negocio (ej. líneas de producción) |

**Recomendación general (a validar contra la planta real):** priorizar submedición dedicada para las máquinas cuya disponibilidad individual importa al negocio, y reservar la desagregación algorítmica para cargas secundarias/auxiliares donde el costo de instrumentación no se justifica.

---

## 7. Comparación Reglas vs. Aprendizaje Automático

| | Reglas (umbral + tiempo mínimo) | ML supervisado |
|---|---|---|
| Qué necesita para arrancar | Nada, solo definir el umbral (o calibrarlo por histograma, sección 5) | Datos ya etiquetados (marcha/parada/tipo) |
| Interpretabilidad | Total | Baja (modelos complejos son caja opaca) |
| Precisión ante casos raros | Baja — un caso no previsto se clasifica siempre mal igual | Alta, si el caso estuvo representado en el entrenamiento |
| Mantenimiento | Ajuste manual de umbrales si cambia el proceso | Reentrenable con datos nuevos |
| Distingue programada/no programada | No por sí sola — necesita cruce con calendario externo | Podría aprenderlo indirectamente solo si el patrón de consumo difiere y esa diferencia está en las etiquetas |
| Rol en esta arquitectura | Motor inicial + generador de etiquetas | Capa posterior, entrenada sobre clasificaciones de reglas corregidas por humanos |

**Idea central:** el ML no reemplaza a las reglas, se apoya en ellas. Reglas clasifican → un humano corrige los errores que ve → esas correcciones acumuladas son el dataset de entrenamiento → recién ahí se entrena un modelo simple (árbol de decisión, regresión logística — antes que redes neuronales), evaluado siempre contra la clasificación por reglas vigente. El modelo se adopta solo si mejora de forma consistente; las reglas quedan como respaldo permanente.

---

## 8. Roadmap de implementación (secuencial)

1. **Segmentación modal y calibración de umbrales:** motor `SegmentadorRegimenesService` (bins log, persistencia topológica, barrido de ancho de banda, dinámicas $|\Delta P|$ y estacionariedad). `CalibradorUmbralService` se apoya en este motor para inferir el umbral marcha/parada de máquinas individuales ($k=2$).
2. **Motor de reglas de disponibilidad:** clasificar eventos instantáneos en marcha/parada según umbral calibrado con filtro anti-transitorios (`FiltroPersistenciaEstadoService`). Cruce con calendario de paradas programadas.
3. **Corrección humana y feedback loop:** endpoint para corregir clasificaciones erróneas guardando autoría y motivo, construyendo el dataset etiquetado.
4. **Desagregación NILM y modelos de estados:** ~~extensión con $k > 2$ para medidores agregados~~ **[implementado]** — ver [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md) y el contexto `src/domain/cargas/`. Queda pendiente la exploración de modelos HSMM supervisados sobre el historial etiquetado, que ahora sí tiene de dónde salir: las correcciones humanas sobre `load_activity_intervals`.

Para medidores que agregan varias cargas (sección 6), este roadmap aplica **por carga o por línea**, no por medidor — lo que exige primero decidir, caso por caso, si corresponde desagregación algorítmica o submedición dedicada.

---

## 9. Fuera de alcance de este documento

- ~~Diseño del modelo de datos~~ **[resuelto]** para disponibilidad (`machines`, `machine_availability_events`, `scheduled_stops`) y para desagregación de cargas (`loads`, `characterization_campaigns`, `campaign_samples`, `load_activity_intervals`).
- ~~Punto de enganche técnico~~ **[resuelto]**: disponibilidad evalúa por evento en la ingesta; la desagregación de cargas corre **batch**, porque la duración de un encendido es parte de su identidad y en vivo no se conoce hasta que terminó.
- Formato concreto de integración con el calendario externo de mantenimiento.
- ~~Selección de algoritmo específico de NILM y su implementación~~ **[resuelto]**, ver [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md). GMM y HSMM siguen pendientes.
