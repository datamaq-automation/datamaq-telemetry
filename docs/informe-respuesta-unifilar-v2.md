# Dictamen Técnico y Respuesta de Delegación: Activación del Diagrama Unifilar (/unifilar)

> **Destino:** Frontend SPA (`app-datamaq`)  
> **Origen:** Equipo de Backend (`datamaq-telemetry`)  
> **Fecha:** 2026-09-19  
> **Estado:** Implementado, Validado con Gauntlet y Desplegable (`NodoUnifilarDTO v2`)  
> **Referencias:** ANSI/ISA-95, IEC 60617, ISO 50001, `docs/informe-respuesta-tgbt-permisos-planta.md`  

---

## 1. Resumen Ejecutivo

El equipo de Backend de `datamaq-telemetry` ha analizado la **Solicitud de Delegación Técnica** remitida por el equipo de Frontend SPA e **implementó de forma completa e inmediata** las extensiones del modelo de dominio, la persistencia declarativa GitOps (`data/organizaciones.yml`), los mappers y el contrato de API `NodoUnifilarDTO v2`.

Todos los cambios fueron validados localmente superando el **Gauntlet pre-push estricto** (0 errores de Pyright, 0 advertencias de Ruff, 100% de reglas Clean Architecture/DDD y 91.13% de cobertura en 1313 tests unitarios y 59 de integración).

---

## 2. Resolución Técnica de las 4 Brechas (Gaps)

### Gap 1: Coordenadas y Geometría 2D (Layout Espacial)
* **Dictamen:** Se adoptó una **Estrategia Híbrida (Opción 1.A + Opción 1.B)**.
* **Fundamento:** 
  1. No todo cliente o planta cuenta inmediatamente con coordenadas manuales ajustadas.
  2. Cada nodo en `NodoUnifilarDTO` ahora incluye el objeto opcional `coordenadas: CoordenadasNodoUnifilarDTO | null` (`x`, `y`, `ancho`, `orientacion: "horizontal" | "vertical"`).
  3. Al mismo tiempo, se garantiza y parsea el campo `orden: int` (secuencial $0, 1, 2, \dots$ de izquierda a derecha por nivel jerárquico).
* **Directiva para Frontend:**
  * Si el nodo posee `coordenadas` definidas (como ocurre ahora en Planta Durax), el lienzo SVG posiciona directamente la barra o el alimentador.
  * Si `coordenadas` es `null` o parcial, el cliente aplica el algoritmo de Auto-Layout esquemático (tipo Sugiyama o Dagre) respetando estrictamente el campo `orden`.

---

### Gap 2: Parámetros Electrotécnicos de Placa (Ingeniería de Instalación)
* **Dictamen:** Se incorporó el objeto fuertemente tipado pero extensible `metadatos_placa: MetadatosPlacaDTO | null` tanto en el Dominio (`MetadatosPlaca` Value Object inmutable) como en el DTO Pydantic (`extra="allow"`).
* **Parámetros soportados y normalizados:**
  * **Transformadores:** `potencia_nominal_kva`, `relacion_tension_kv` (ej. `"13.2 / 0.4 kV"`), `vsc_porcentaje` (ej. `4.0`), `grupo_conexion` (ej. `"Dyn11"`).
  * **Barras y Tableros (TGBT / Seccionales):** `corriente_nominal_a` (o `corriente_barra_a`), `icw_ka` (ej. `50.0`), `frecuencia_hz` (`50.0`), `proteccion_in_a`, `trafo_asociado_kva`.
  * **Alimentadores / Circuitos:** `calibre_in_a`, `cable_seccion` (ej. `"3x(1x185) + 95 mm² XLPE Cu"`), `longitud_estimada_m`.
  * **Generales / Tarifarios:** `tension_nominal_v`, `categoria_tarifaria` (ej. `"T3-MT"`).
  * **Compatibilidad de Nombres:** El modelo normaliza automáticamente variantes en mayúscula (`in_A`, `icu_kA`, `corriente_nominal_A`, `calibre_in_A`) tanto en YAML como en JSON.

---

### Gap 3: Órganos de Maniobra y Protección (Interruptores)
* **Dictamen:** Se seleccionó de forma contundente la **Opción 2: Atributos de protección y maniobra embebidos (`interruptor_cabecera`)**.
* **Fundamento electrotécnico y de arquitectura:**
  1. En sistemas SCADA y de telemetría de energía, los interruptores generales (ACB, MCCB, seccionadores) rara vez poseen un medidor de potencia independiente (`device_id`); su estado es de apertura/cierre o de placa nominal.
  2. Modelar interruptores como nodos independientes en el grafo (`nodos[]`) duplicaría la profundidad del árbol (`Acometida -> Interruptor MT -> Trafo -> Interruptor BT -> Barra TGBT -> Interruptor Salida -> Carga`), quebrando la agregación de telemetría de medidores frontera de la norma ISO 50001 (`ArbolUnifilarService.medidores_frontera()`).
  3. En `NodoUnifilarDTO v2`, cada nodo puede incluir:
     ```json
     "interruptor_cabecera": {
       "tag": "Q0-USINA",
       "tipo": "ACB",
       "in_a": 1600.0,
       "icu_ka": 65.0,
       "estado": "cerrado"
     }
     ```
  4. El componente gráfico SVG puede dibujar el símbolo del interruptor exactamente en la acometida/cabecera del tablero o tramo correspondiente sin saltos de grafo artificiales.

---

### Gap 4: Saneamiento de Redundancia 1:1 en Topología (Trafo ↔ TGBT)
* **Dictamen:** **NO se aplanan los transformadores en el YAML**; en su lugar, se expone el flag discriminador **`es_pasante: bool`** (`true` en transformadores de enlace 1:1, `false` en TGBTs medidos).
* **Fundamento físico y electrotécnico ineludible:**
  1. Conectar físicamente un TGBT (380 V) directamente como hijo de una Acometida MT (13.2 kV) omitiendo el centro de transformación viola las leyes de la física y la norma IEC 60617: no existe enlace galvánico directo entre MT y BT sin transformación electromagnética.
  2. Si una subestación posee dos transformadores en paralelo alimentando una barra común (caso real de Usina Durax), o si a futuro se instrumenta un analizador en MT, el modelo aplanado colapsaría.
  3. Para resolver la queja del frontend (duplicación visual de bloques idénticos):
     * El backend calcula y marca `es_pasante: true` en todo nodo virtual intermedio sin medidor propio que posea un solo hijo (o declarado explícitamente como pasante).
     * **Instrucción para el Frontend:** Los nodos con `es_pasante: true` (ej. `nodo-durax-trifasico-1`) **NO deben renderizarse como una caja/tarjeta de tablero duplicada**. Deben renderizarse como el **símbolo eléctrico vectorial del componente en línea** (dos círculos entrelazados de transformador $\mathbin{\&}$ o símbolo IEC de trafo) sobre el conductor que baja de la barra MT hacia la barra del TGBT.

---

## 3. Contrato de Respuesta Actualizado (`NodoUnifilarDTO v2`)

Endpoint: `GET /api/v1/planta/unifilar` (o `GET /api/v1/plantas/{planta_id}/unifilar`)

### Ejemplo Real: Planta Durax (`c64fd625-0037-4caa-b68a-800e8e0ee548`)

```json
{
  "planta_id": "c64fd625-0037-4caa-b68a-800e8e0ee548",
  "nombre_planta": "Vajillas Durax S.A.",
  "topologia_valida": true,
  "nodos": [
    {
      "id": "nodo-durax-acometida-mt",
      "parent_id": null,
      "nombre": "Acometida MT",
      "tipo": "acometida",
      "device_id": null,
      "es_virtual": true,
      "es_pasante": false,
      "nombre_maquina": null,
      "tension_nominal_V": 13200.0,
      "nivel_tension": "MT",
      "capacidad_nominal_kVA": null,
      "potencia_nominal_kw": null,
      "uso_significativo": false,
      "categoria_uso": null,
      "variable_relevante": null,
      "orden": 0,
      "fuente_dato": "Confirmación en campo (2026-09-12)",
      "notas_metrologicas": "Acometida virtual de MT calculada por suma de medidores frontera",
      "coordenadas": {
        "x": 250.0,
        "y": 50.0,
        "ancho": 300.0,
        "orientacion": "horizontal"
      },
      "metadatos_placa": {
        "tension_nominal_v": 13200.0,
        "categoria_tarifaria": "T3-MT",
        "frecuencia_hz": 50.0
      },
      "interruptor_cabecera": {
        "tag": "QM-01",
        "tipo": "SECCIONADOR_MT",
        "in_a": null,
        "icu_ka": null,
        "estado": "cerrado"
      }
    },
    {
      "id": "nodo-durax-trifasico-1",
      "parent_id": "nodo-durax-acometida-mt",
      "nombre": "Transformación Usina (2 trafos en paralelo)",
      "tipo": "transformador",
      "device_id": null,
      "es_virtual": true,
      "es_pasante": true,
      "nombre_maquina": null,
      "tension_nominal_V": 380.0,
      "nivel_tension": "BT",
      "capacidad_nominal_kVA": null,
      "potencia_nominal_kw": null,
      "uso_significativo": false,
      "categoria_uso": null,
      "variable_relevante": null,
      "orden": 1,
      "fuente_dato": "Relevamiento de planta Cristal Avellaneda (2026-09-13)",
      "notas_metrologicas": "Grupo de 2 transformadores en paralelo sobre la misma barra de BT",
      "coordenadas": {
        "x": 150.0,
        "y": 150.0,
        "ancho": null,
        "orientacion": null
      },
      "metadatos_placa": {
        "potencia_nominal_kva": 1000.0,
        "relacion_tension_kv": "13.2 / 0.4 kV",
        "vsc_porcentaje": 4.0,
        "grupo_conexion": "Dyn11",
        "frecuencia_hz": 50.0
      },
      "interruptor_cabecera": null
    },
    {
      "id": "nodo-durax-powermeter-bf2c",
      "parent_id": "nodo-durax-acometida-mt",
      "nombre": "Transformación Horno (2 trafos en paralelo)",
      "tipo": "transformador",
      "device_id": null,
      "es_virtual": true,
      "es_pasante": true,
      "nombre_maquina": null,
      "tension_nominal_V": 380.0,
      "nivel_tension": "BT",
      "capacidad_nominal_kVA": null,
      "potencia_nominal_kw": null,
      "uso_significativo": false,
      "categoria_uso": null,
      "variable_relevante": null,
      "orden": 2,
      "fuente_dato": "Relevamiento de planta Cristal Avellaneda (2026-09-13)",
      "notas_metrologicas": "Grupo de 2 transformadores en paralelo sobre la misma barra de BT",
      "coordenadas": {
        "x": 350.0,
        "y": 150.0,
        "ancho": null,
        "orientacion": null
      },
      "metadatos_placa": {
        "potencia_nominal_kva": 1000.0,
        "relacion_tension_kv": "13.2 / 0.4 kV",
        "vsc_porcentaje": 4.0,
        "grupo_conexion": "Dyn11",
        "frecuencia_hz": 50.0
      },
      "interruptor_cabecera": null
    },
    {
      "id": "nodo-durax-tgbt-usina",
      "parent_id": "nodo-durax-trifasico-1",
      "nombre": "TGBT Usina",
      "tipo": "tgbt",
      "device_id": "51048a93-f1f3-4283-a708-24cbd39c7192",
      "es_virtual": false,
      "es_pasante": false,
      "nombre_maquina": null,
      "tension_nominal_V": 380.0,
      "nivel_tension": "BT",
      "capacidad_nominal_kVA": null,
      "potencia_nominal_kw": null,
      "uso_significativo": true,
      "categoria_uso": "FUERZA_MOTRIZ",
      "variable_relevante": null,
      "orden": 1,
      "fuente_dato": "Verificado con pinza amperométrica en barra BT (2026-09-13)",
      "notas_metrologicas": "TI sobre secundario de sumador del banco; reactiva medida ya compensada",
      "coordenadas": {
        "x": 150.0,
        "y": 250.0,
        "ancho": 160.0,
        "orientacion": "horizontal"
      },
      "metadatos_placa": {
        "trafo_asociado_kva": 1000.0,
        "corriente_barra_a": 1600.0,
        "icw_ka": 50.0,
        "proteccion_in_a": 1600.0,
        "frecuencia_hz": 50.0
      },
      "interruptor_cabecera": {
        "tag": "Q0-USINA",
        "tipo": "ACB",
        "in_a": 1600.0,
        "icu_ka": 65.0,
        "estado": "cerrado"
      }
    },
    {
      "id": "nodo-durax-tgbt-horno",
      "parent_id": "nodo-durax-powermeter-bf2c",
      "nombre": "TGBT Horno",
      "tipo": "tgbt",
      "device_id": "b5f4bcd6-b017-4796-bb3d-efcfb50dc8f0",
      "es_virtual": false,
      "es_pasante": false,
      "nombre_maquina": null,
      "tension_nominal_V": 380.0,
      "nivel_tension": "BT",
      "capacidad_nominal_kVA": null,
      "potencia_nominal_kw": null,
      "uso_significativo": true,
      "categoria_uso": "CALOR_PROCESO",
      "variable_relevante": null,
      "orden": 2,
      "fuente_dato": "Relevamiento de planta Cristal Avellaneda (2026-09-13)",
      "notas_metrologicas": "Horno de fusión continuo de vidrio; uso térmico intensivo",
      "coordenadas": {
        "x": 350.0,
        "y": 250.0,
        "ancho": 160.0,
        "orientacion": "horizontal"
      },
      "metadatos_placa": {
        "trafo_asociado_kva": 1000.0,
        "corriente_barra_a": 1600.0,
        "icw_ka": 50.0,
        "proteccion_in_a": 1600.0,
        "frecuencia_hz": 50.0
      },
      "interruptor_cabecera": {
        "tag": "Q0-HORNO",
        "tipo": "ACB",
        "in_a": 1600.0,
        "icu_ka": 65.0,
        "estado": "cerrado"
      }
    }
  ]
}
```

---

## 4. Guía de Consumo e Implementación en Frontend SPA

1. **Activación de `/unifilar`:**
   * Al recibir `topologia_valida: true`, la vista `/unifilar` puede levantarse de inmediato (`topologiaConfigurada = true`).
2. **Interpretación de Nodos:**
   * **Barras y Tableros (`tipo in ["acometida", "tgbt", "seccional", "carga"]` y `es_pasante == false`):**
     Renderizar como barras colectoras horizontales/verticales con su título, etiqueta de tensión (`MT` / `BT`), telemetría de `/resumen` (kW, FP) e interruptor de cabecera si existe (`interruptor_cabecera.tag`).
   * **Nodos Pasantes (`es_pasante == true` o `tipo == "transformador"`):**
     Renderizar como el **símbolo electrotécnico del transformador en la línea de enlace** entre el padre (Acometida MT) y el hijo (TGBT). Mostrar al pasar el cursor o en el panel lateral los `metadatos_placa` (kVA, relación de transformación $13.2 / 0.4\text{ kV}$, $V_{sc}\%$, grupo de conexión Dyn11).
3. **Panel Lateral de Ingeniería:**
   * Al hacer click en cualquier barra o transformador, volcar las propiedades de `metadatos_placa` e `interruptor_cabecera` en el inspector lateral para brindar valor técnico de ingeniería a los operadores de planta.
