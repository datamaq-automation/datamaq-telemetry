# Auditoría de Brechas ISO 50001:2018 (SGE) y Hoja de Ruta Técnica

> **Repositorio:** `datamaq-telemetry` / `datamaq`  
> **Estándares:** ISO 50001:2018 (SGE) / ISO 50006:2014/2023 (EnPI y EnB) / ANSI/ISA-95  
> **Estado:** Documento de Arquitectura y Referencia Normativa  
> **Fecha:** 2026-09-19

---

## 1. Objetivo y Alcance

Este documento establece la auditoría de brechas (*Gap Analysis*) entre la plataforma actual de telemetría de DataMaq y los requisitos normativos exigidos para certificar y operar un **Sistema de Gestión de la Energía (SGE) conforme a la norma internacional ISO 50001:2018**.

El objetivo es asegurar que la plataforma provea la evidencia objetiva, repetible y auditable que exige un auditor de tercera parte (ej. IRAM, TÜV, DNV, Bureau Veritas).

---

## 2. Matriz de Cumplimiento por Cláusulas ISO 50001:2018

| Cláusula ISO 50001 | Requisito Normativo | Estado en DataMaq | Artefacto / Código de Soporte |
|---|---|:---:|---|
| **4.3** Alcance y Límites | Delimitar la frontera física y organizativa del SGE | **CUMPLIDO** | Jerarquía GitOps en `data/organizaciones.yml` (Organización $\to$ Planta $\to$ Nodo $\to$ Medidor) |
| **5.2** Política Energética | Marco para objetivos y metas energéticas | **CUMPLIDO** | `src/domain/sge/entities.py` (`ArticuloSge` categorizado) |
| **6.3** Revisión Energética | Identificar usos significativos de energía (SEU/USE) | **PARCIAL** | Metadatos en `NodoUnifilar` (`uso_significativo`, `categoria_uso`). **Falta:** Balance formal de energía en TGBT (Sankey) |
| **6.4** Indicadores de Desempeño (EnPI) | Cuantificar el desempeño frente a Variables Relevantes | **CUMPLIDO** | `CalculadorEnPIService` (`src/domain/produccion/`) con Consumo Específico (**SEC**: kWh/m y kWh/corte) |
| **6.5** Línea de Base (EnB) | Establecer período de referencia para cuantificar el desempeño | **PARCIAL** | Se calcula perfil basal de potencia, pero **falta congelar formalmente los parámetros de la EnB** |
| **6.6** Plan de Recopilación de Datos | Metrología periódica y trazable de variables clave | **CUMPLIDO** | Ingesta cuatridimensional ($P, Q, S, \cos \phi$), corrección fasorial de software y calibración en YAML |
| **9.1** Seguimiento, Medición y Análisis | Demostrar la **mejora del desempeño energético** en el tiempo | **PENDIENTE** | **Falta:** Algoritmo determinístico de ahorros ($E_{\text{EnB}} - E_{\text{real}}$) y gráfico CUSUM |

---

## 3. Diagnóstico de Certezas, Dudas y Redundancias

### A. Certezas Técnicas (Hechos Verificados en Código y Física)
1. **La medición cuatridimensional es sólida:** La base de datos y los gateways ingieren $P, Q, S, \cos \phi$ reales.
2. **Los motores industriales siguen física predecible:** `ModeloMotorFisicoService` mapea regímenes de carga por factor de carga ($LF = P/P_{nom}$) y corriente de magnetización reactiva con $100\%$ de interpretabilidad.
3. **Las variables de proceso eliminan la conjetura:** Los sensores inductivos de avance y corte son la *Variable Relevante* de la ISO 50001; al cruzarse con el consumo eléctrico, el Consumo Específico (**SEC**) es un cálculo aritmético directo sin márgenes de error.
4. **El balance en TGBT es determinístico:** En un transformador, la diferencia entre la energía de cabecera y los subtableros debe ser igual a las pérdidas técnicas de trafo y cables ($1\%\text{--}4\%$). Un residual mayor delata consumos no declarados.
5. **Una Línea de Base (EnB) auditable debe ser congelada:** No puede mutar indefinidamente. Se define un período de calibración histórico y sus coeficientes quedan fijos para comparar los períodos futuros.

### B. Dudas Abiertas (A validar con la operación de planta)
1. **Punto de conexión física de sensores inductivos:** Si se conectan como entradas digitales GPIO en el propio microcontrolador (ESP32 del Powermeter) enviando pulsos en el mensaje MQTT, o si provienen de un PLC / gateway secundario.
2. **Ciclo de revisión de la Línea de Base:** Si la organización reajusta la EnB anualmente o por cambios de proceso (nuevos productos, ampliación de planta) según su procedimiento documentado del SGE.
3. **Trazabilidad metrológica:** Si la planta cuenta con fotos de placa y certificados de clase de precisión (0.5S, 1.0) de los TI instalados en cabecera de trafo.

### C. Redundancias Técnicas a Purgar
1. **Heurísticas residenciales en medidores industriales:** Las reglas de heladeras, caloventores, pavas eléctricas y PCs (`CatalogoPresetsCargas` y `ClasificadorCargasReglasService`) son un factor de ruido en un transformador de 500 kVA. Se aíslan al contexto residencial.
2. **Fragmentación `Maquina` vs `Carga`:** En la base conviven `machines` (para OEE de paradas) y `loads` (para catálogo de potencia). En la ISO 50001, una máquina es un único activo con indicadores OEE y EnPI combinados.

---

## 4. Hoja de Ruta Técnica de Cierre

1. **Balance de Energía Unifilar (`BalanceEnergiaService`):**
   * Endpoint y servicio que evalúa:
     $$E_{\text{residual}} = E_{\text{TGBT}} - \sum E_{\text{seccionales}}$$
   * Diagnóstico: si $E_{\text{residual}} \le 0.04 \times E_{\text{TGBT}} \implies$ Pérdidas técnicas normales. Si supera el $4\% \implies$ Alerta de fuga o carga clandestina.
2. **Cálculo de Ahorros y Control CUSUM (`CalculadorAhorrosIsoService`):**
   * Dado un período de reporte con volumen $V$ y una EnB congelada:
     $$E_{\text{esperada}} = \text{SEC}_{\text{EnB}} \times V$$
     $$\text{Ahorro} = E_{\text{esperada}} - E_{\text{real}}$$
   * Acumulación temporal: $\text{CUSUM}(t) = \sum \text{Ahorro}(i)$.
3. **Aislamiento de Módulos:**
   * Crear la división explícita entre presets residenciales y presets industriales para garantizar que la plataforma industrial permanezca $100\%$ enfocada en SEUs industriales.
