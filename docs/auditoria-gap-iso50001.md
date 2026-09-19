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
| **6.3** Revisión Energética | Identificar usos significativos de energía (SEU/USE) y calidad eléctrica | **PARCIAL** | Metadatos en `NodoUnifilar`. `BalanceEnergiaService` listo en dominio. **Falta:** Exponer balance TGBT en API e incorporar **Distorsión Armónica Total ($THD_V, THD_I$)** para evaluar pérdidas térmicas parásitas en trafo/cables. |
| **6.4** Indicadores de Desempeño (EnPI) | Cuantificar el desempeño frente a Variables Relevantes | **CUMPLIDO** | `CalculadorEnPIService` (`src/domain/produccion/`) con Consumo Específico (**SEC**: kWh/m y kWh/corte) |
| **6.5** Línea de Base (EnB) | Establecer período de referencia para cuantificar el desempeño | **CUMPLIDO (Diseño)** | Definida y autorizada por `admin`/`superadmin`. Se congela formalmente como SSOT en `data/organizaciones.yml` (GitOps) con `CalculadorAhorrosIsoService`. |
| **6.6** Plan de Recopilación de Datos | Metrología periódica y trazable de variables clave y de proceso | **CUMPLIDO** | Ingesta cuatridimensional ($P, Q, S, \cos \phi$), corrección fasorial de software y sensórica inductiva conectada al PLC/controlador IoT **Automate** de Powermeter. |
| **9.1** Seguimiento, Medición y Análisis | Demostrar la **mejora del desempeño energético** en el tiempo | **PARCIAL** | `CalculadorAhorrosIsoService` implementado en dominio. **Falta:** Exponer serie temporal CUSUM en API y UI. |

---

## 3. Diagnóstico de Certezas, Dudas y Redundancias

### A. Certezas Técnicas y de Gobernanza (Hechos Verificados en Código, Física y Arquitectura)
1. **La medición cuatridimensional es sólida:** La base de datos y los gateways ingieren $P, Q, S, \cos \phi$ reales con corrección fasorial de software.
2. **La Distorsión Armónica Total ($THD_V$ y $THD_I$) es crítica (IEEE 519 / IEC 61000-4-30):** Las corrientes armónicas elevan las pérdidas Joule parásitas ($I_{\text{rms}}^2 \cdot R$) en cables y transformador, provocan calentamiento y exigen *derating* en motores trifásicos, justificando desvíos de pérdidas en el balance del TGBT sin aportar trabajo mecánico útil.
3. **El hardware de proceso es Powermeter Automate:** Los sensores físicos inductivos (pulsos de corte y avance métrico) se conectan a un controlador/PLC IoT industrial **Automate** (de Powermeter S.A.S.), desacoplado físicamente del medidor eléctrico.
4. **Gobernanza y persistencia de EnB por GitOps:** La definición y autorización de la Línea de Base Energética (EnB) corresponde a los roles `superadministrador` y `administrador`. Se configura y congela formalmente en `data/organizaciones.yml` para garantizar inmutabilidad, trazabilidad por git y reproducibilidad ante auditorías.
5. **Los motores industriales siguen física predecible:** `ModeloMotorFisicoService` mapea regímenes de carga por factor de carga ($LF = P/P_{nom}$) y reactiva de magnetización con 100% de interpretabilidad.
6. **El Consumo Específico (SEC) es determinístico:** Al cruzar la energía ($kWh$) con las lecturas inductivas de Automate, el SEC es un cálculo aritmético directo sin margen de conjetura.
7. **El balance en TGBT es determinístico:** La diferencia entre la energía de cabecera y los subtableros debe ser igual a las pérdidas técnicas de trafo y cables ($1\%\text{--}4\%$). Un residual mayor delata consumos no declarados.

### B. Dudas Abiertas (A validar con la operación de planta)
1. **Calibración de pérdidas según trafo:** Ajuste fino del umbral de pérdidas técnicas según potencia (kVA) y antigüedad del transformador en cada planta.
2. **Trazabilidad metrológica:** Si la planta cuenta con fotos de placa y certificados de clase de precisión (0.5S, 1.0) de los TI instalados en cabecera de trafo.

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
