# Disponibilidad de Máquina a partir del Comportamiento Energético — Diseño Conceptual

> **Estado:** Documento de diseño conceptual. No describe código existente ni un plan de implementación con tablas/servicios definidos — es la base de razonamiento para una futura sesión de diseño técnico.
> **Origen:** Sesión de diseño 2026-09-02/03, orientada a evaluar cómo derivar disponibilidad de máquina (marcha / parada programada / parada no programada) a partir de las variables eléctricas que ya captura la plataforma.

---

## 1. Objetivo y alcance

Datamaq Telemetry mide hoy variables eléctricas por medidor (potencia, corriente, tensión, energía acumulada) y evalúa calidad de energía. El objetivo de este documento es sentar las bases conceptuales para, a partir de ese comportamiento energético, **inferir indirectamente la disponibilidad de las máquinas**: tiempo en marcha, tiempo de parada programada y tiempo de parada no programada.

Este documento **no define** todavía tablas, servicios ni endpoints — es intencionalmente conceptual, para alinear criterio antes de comprometer un diseño técnico.

---

## 2. Punto de partida: qué existe hoy en la plataforma

Relevado sobre el modelo de datos y el código de ingesta (`src/infrastructure/sqlalchemy/models.py`, `src/application/use_cases/ingestar_telemetria.py`):

- **`telemetry_instantaneous`**: potencia activa/reactiva/aparente, corriente y tensión por fase y totales, cada ~5 minutos en modo estándar (soporta modo ráfaga de 1-5s vía `realtime_sync_mode` para una máquina puntual).
- **`telemetry_energy`**: contadores acumulados de energía activa/reactiva.
- **`device_status_logs` / `EstadoDispositivo`**: conectividad del medidor (ONLINE/OFFLINE/WARNING) — **no** es un estado de proceso productivo.
- **`device_alerts`**: alertas de calidad eléctrica (desbalance, THD, factor de potencia) — no de disponibilidad de máquina.
- **No existe** ninguna entidad "Máquina/Equipo" separada del medidor, ningún estado de marcha/parada, ni calendario de paradas programadas o turnos dentro del sistema.
- La relación medidor↔máquina en la planta real es **mixta**: algunos medidores miden una única máquina; otros agregan una línea/tablero con varias cargas juntas.
- El calendario de paradas programadas (mantenimiento, cambios de turno) existe hoy **fuera del sistema** (ERP/mantenimiento externo) — se podría cruzar por fecha/hora, pero no hay integración.
- Ya existe en el dominio un patrón reutilizable para filtrar ruido temporal: `FiltroPersistenciaTemporalService`, que exige N lecturas consecutivas o M segundos antes de confirmar una alerta (evita reaccionar a un transitorio puntual). El mismo principio aplica conceptualmente a la detección de cambios de estado de marcha/parada.

---

## 3. Certezas

1. **La disponibilidad es un estado de 3 valores, no 2:** marcha / parada programada / parada no programada. La señal eléctrica **nunca** alcanza sola para distinguir "programada" de "no programada" — eso es información de planificación (calendario, turnos, órdenes de mantenimiento), no de energía. Requiere cruzar la clasificación eléctrica con una fuente externa por fecha/hora.
2. **Un enfoque por reglas (umbrales de potencia) es el punto de partida correcto**, no un atajo inferior al aprendizaje automático. Es interpretable, auditable, no requiere datos históricos etiquetados, y es el estándar de la industria (OEE/TPM) antes de cualquier capa de ML.
3. **El ML supervisado necesita "verdad de terreno" (ground truth) para entrenar, y hoy no existe.** Las reglas son la forma de generar las primeras etiquetas (con ruido) para arrancar un dataset histórico; el ML no reemplaza a las reglas, se apoya en ellas.
4. **La cadencia real de datos (5 min estándar) define el piso de resolución temporal.** Un micro-paro de 30 segundos no se puede detectar como evento propio salvo activar el modo ráfaga para esa máquina puntual.
5. **El umbral marcha/parada se puede calibrar empíricamente, no adivinado**, a partir del histograma de potencia de cada máquina (ver sección 5).
6. **Cuando un medidor agrega varias cargas independientes**, el problema deja de ser "marcha vs. parada" (2 estados) y pasa a ser un problema de **desagregación de cargas** (ver sección 6), con su propia complejidad y límites de confiabilidad.
7. **El conocimiento físico del proceso reduce el espacio de estados posible** y debe inyectarse como restricción de diseño, no esperarse que un algoritmo lo "descubra" solo (ej.: si una línea de producción depende neumáticamente del compresor, el estado "línea activa sin compresor" no es un estado válido a considerar).

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

## 5. Calibración de umbrales por histograma de potencia

### 5.1 Por qué el histograma es la herramienta correcta

Para una máquina que alterna entre parada y marcha, el histograma de sus lecturas de potencia (eje X = potencia, eje Y = frecuencia de lecturas) tiende a ser **bimodal**: una campana angosta cerca del consumo de parada/standby, y otra más ancha centrada en la potencia operativa típica. El **valle** entre ambas campanas es el umbral que minimiza la clasificación errónea — es la misma idea detrás del método clásico de Otsu en procesamiento de imágenes.

### 5.2 Escala logarítmica en el eje de frecuencia

Si la máquina pasa mucho más tiempo en un estado que en otro (ej. 80% parada / 20% en marcha), en escala lineal la campana minoritaria queda achatada contra el eje y el valle es difícil de ubicar, tanto visualmente como para un algoritmo de detección de mínimos locales. Usar **escala logarítmica en el eje de frecuencia** comprime la campana dominante y hace visible la campana minoritaria con la misma nitidez.

### 5.3 Suavizado previo

Un histograma crudo es ruidoso: fluctuaciones estadísticas generan mini-picos y mini-valles falsos que no corresponden a estados reales. Antes de buscar picos/valles hace falta suavizar (promedio móvil sobre bins, o una curva continua vía estimación de densidad por kernel — KDE). El rol de este suavizado es equivalente, a nivel de la forma de la distribución, al que cumple `FiltroPersistenciaTemporalService` a nivel de la serie temporal: filtrar ruido transitorio antes de tomar una decisión de clasificación.

### 5.4 Rol de promedio y mediana — y su límite

- El **promedio** de toda la serie no sirve para encontrar el umbral en una distribución bimodal: cae en un punto intermedio entre ambas campanas que no representa ningún estado real.
- La **mediana** tampoco separa las campanas: solo indica en cuál cae más del 50% de las lecturas.
- Donde sí son útiles: **una vez clasificado** cada intervalo (marcha/parada) mediante el umbral del valle, calcular la mediana de potencia **dentro de cada grupo por separado** da una estadística robusta de "potencia operativa típica" (menos sensible a picos anómalos puntuales que el promedio) — útil para dashboards y para detectar degradación del proceso a lo largo del tiempo, no para trazar la frontera entre categorías.

### 5.5 Relación con técnicas estadísticas más rigurosas

Este método (encontrar dos modos y el valle entre ellos sobre una curva suavizada) es la versión más simple de un problema estadístico más general: **ajustar un Modelo de Mezcla Gaussiana (GMM) de 2 componentes** a los datos. Cuando las campanas se superponen mucho o el histograma es ambiguo, GMM da el punto de cruce de forma matemáticamente más robusta que buscar un mínimo local a ojo. Es un método **no supervisado** (no requiere etiquetas humanas) — un escalón intermedio entre "umbral fijo a mano" y "ML supervisado con etiquetas".

---

## 6. Medidores que agregan varias cargas: desagregación de cargas (NILM)

### 6.1 El problema

Ejemplo real de referencia: un medidor que agrega iluminación + compresor + línea de producción 1 + línea de producción 2. Con **n cargas independientes**, el número de combinaciones posibles de encendido/apagado es **2ⁿ** (con 4 cargas, hasta 16 estados teóricos) — el histograma bimodal de la sección 5 deja de alcanzar, porque ya no hay 2 estados sino potencialmente muchos.

Este es el problema clásico de **desagregación de cargas no intrusiva (NILM — Non-Intrusive Load Monitoring)**, estudiado desde los años 80 (Hart, 1992) para inferir qué electrodomésticos/cargas están activos a partir de un único medidor agregado.

### 6.2 Dos técnicas, con condiciones de éxito distintas

**Técnica A — Clustering por nivel de potencia.**
Generaliza el histograma bimodal a un agrupamiento de hasta k modos (ej. k-means), uno por combinación de cargas activas. Funciona si cada combinación produce un nivel de potencia total estable y suficientemente distinto de las demás. Falla si dos combinaciones distintas dan sumas parecidas, o si alguna carga tiene potencia variable (no fija) mientras está activa.

**Técnica B — Detección de eventos/escalones (ΔP).**
En vez de mirar el nivel, mirar el **cambio** de potencia entre lecturas consecutivas. Cada carga que se prende/apaga produce un salto (escalón) de tamaño aproximadamente igual a su potencia característica ("firma"). Si se conoce la firma de cada carga, se puede atribuir cada escalón observado a la carga correspondiente sin enumerar todas las combinaciones de antemano. Es la técnica original de Hart. Falla si las cargas no tienen firma estable, o si dos cargas se prenden/apagan simultáneamente (el escalón combinado no se puede separar sin ambigüedad).

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

## 8. Roadmap propuesto (secuencial)

1. **Motor de reglas.** Clasificar cada intervalo en marcha/parada según un umbral de potencia calibrado por máquina (histograma, sección 5), con ventana mínima de persistencia (patrón `FiltroPersistenciaTemporalService`). Cruzar cada intervalo de parada con el calendario externo para resolver programada/no-programada.
2. **Corrección humana.** Permitir que un operario/supervisor corrija una clasificación puntual. Cada corrección queda guardada como ejemplo etiquetado.
3. **Modelo de ML supervisado.** Con volumen suficiente de intervalos clasificados y corregidos, entrenar un modelo simple e interpretable, evaluado contra la clasificación por reglas. Se adopta solo si mejora de forma medible y consistente.

Para medidores que agregan varias cargas (sección 6), este roadmap aplica **por carga o por línea**, no por medidor — lo que exige primero decidir, caso por caso, si corresponde desagregación algorítmica o submedición dedicada.

---

## 9. Fuera de alcance de este documento

- Diseño del modelo de datos (entidad "Máquina", tabla de eventos de disponibilidad, mecanismo de corrección humana).
- Punto de enganche técnico (evaluación por evento en `IngestarTelemetriaUseCase` vs. job batch).
- Formato concreto de integración con el calendario externo de mantenimiento.
- Selección de algoritmo específico de clustering/GMM/NILM y su implementación.

Estos puntos quedan para una sesión de diseño técnico posterior, una vez relevadas las dudas de la sección 4.
