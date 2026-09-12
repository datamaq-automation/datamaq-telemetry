# Índice Maestro de Documentación Técnica — Datamaq Telemetry

> **Repositorio:** `datamaq-telemetry` (Backend FastAPI, Ingestión MQTT y Motor de Analítica)  
> **Última Actualización:** 2026-09-04  
> **Estado:** Documentación Centralizada y Sincronizada

Bienvenido al centro de documentación técnica del backend de telemetría de energía DataMaq. Los documentos canónicos vivos están organizados temáticamente según el área técnica:

---

## 🗺️ Documentación Canónica Viva

### 1. Integración Frontend & Contratos de API (`app-datamaq`)

* 📄 [`docs/frontend-integration-guide.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/frontend-integration-guide.md)  
  *Guía Canónica de Integración Web / SPA:* Contrato unificado que cubre:
  - **Autenticación:** Sesión por cookie `HttpOnly` (`datamaq_token`), endpoints `/login`, `/logout`, `/me`, acceso stateless `/guest` y matriz de permisos por roles (`admin`, `operador`, `invitado`).
  - **Telemetría en Tiempo Real:** WebSocket `/ws/live` con autenticación en handshake.
  - **Telemetría REST:** `/latest` e `/instantaneous` con remuestreo inteligente (`granularity`).
  - **Analítica de Calidad y Compensación de Reactiva:** Bloque [`AnaliticaCalidadEnergiaDTO`](file:///home/agustin/proyectos_software/datamaq-telemetry/src/application/dtos/telemetria_dto.py#L18-L27) (*Thin Client / Backend SSOT*), dimensionamiento de $Q_c$ (kVAr), catálogo de bancos comerciales, recargo tarifario ENRE en ARS, desbalances $\text{VUR}$/$\text{IUR}$ y estados de red.
  - **Alertas e Incidentes:** `GET /api/v1/alertas` y `PATCH /api/v1/alertas/{id}/resolver`.
  - **Metrología 2-TI:** `PATCH /api/v1/dispositivos/{id}` (`fases_con_ti`, `tipo_instalacion`).
  - **Topología Unifilar y Layout 2D:** `/api/v1/planta/unifilar` y `/api/v1/planta/layout`.

---

### 2. Protocolos de Hardware & Dispositivos IoT (Powermeter ESP32)

* 📄 [`docs/powermeter_mqtt_protocol.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/powermeter_mqtt_protocol.md)  
  *Protocolo MQTT:* Mapa completo de tópicos (`inst`, `acc`, `energyio`, `status`, `event`, `add`, `onoff`, `conf`), esquemas JSON (formatos compacto por fase y extendido), cadencia de publicación (300s estándar / ráfagas sub-minutales), QoS y perfiles de conexión.
* 📄 [`docs/provisioning_guide.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/provisioning_guide.md)  
  *Guía de Aprovisionamiento en Campo:* Procedimiento CLI (`scripts/provision_device.py`) e interfaz web local (`192.168.4.1`) para conectar medidores al servidor propio de Datamaq o restaurar al broker oficial de fábrica. Configuración obligatoria del broker: `mqtt.datamaq.com.ar:8883`, `TLS-SERVER-AUTH` con CA ISRG Root X1 y usuario `datamaq_device`.
* 📄 [`docs/informe-cambios-contrato-telemetria.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/informe-cambios-contrato-telemetria.md)  
  *Informe de Cambios de Contrato (backend → frontend):* Handoff del saneamiento de la API de telemetría — timestamps con offset explícito, estado `SIN_DATOS` en los enums normativos, potencia aparente unificada en $S = V \cdot I$, y umbrales de carga mínima para desbalance de corriente y dimensionamiento de reactiva. Incluye antes/después con datos reales, los contratos TypeScript actualizados y la deuda de contrato pendiente.
* 📄 [`docs/troubleshooting-conectividad-dispositivos.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/troubleshooting-conectividad-dispositivos.md)  
  *Diagnóstico de Conectividad de Medidores:* Árbol de decisión para separar fallo de Wi-Fi vs. fallo de broker, playbook de comandos (log de Mosquitto, barrido de LAN, prueba end-to-end con `mosquitto_pub`, `status.json` del equipo) y bitácora del incidente del 2026-09-01.
* 📄 [`docs/deteccion-anomalias-fases-y-polaridad.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/deteccion-anomalias-fases-y-polaridad.md)  
  *Detección de Anomalías Eléctricas:* Algoritmos matemáticos en dominio para detección automática de inversión de polaridad en transformadores de corriente (`TI_INVERTIDO`), cruce de fases (CT Mismatch) y orden de secuencia de fases ($R-S-T$ vs. $R-T-S$).

---

### 3. Modelo de Datos, Persistencia y Gobernanza

* 📄 [`docs/arquitectura-sge-isa95.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/arquitectura-sge-isa95.md)  
  *Arquitectura de Datos SGE e ISA-95:* Jerarquía industrial de activos (Empresa -> Sitio/Planta -> Área/Topología Eléctrica -> Unidad/Medidor IoT), requisitos de ISO 50001 (Fronteras, USEs, Línea de Base y EnPIs) y persistencia GitOps declarativa en `./data/`.
* 📄 [`docs/database_erd.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/database_erd.md)  
  *Diagrama Entidad-Relación (ERD):* Diagrama Mermaid autogenerado de todas las tablas MySQL, índices B-Tree, columnas de ingeniería y matriz de políticas de retención.
* 📄 [`docs/to_www-datamaq.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/to_www-datamaq.md)  
  *Directiva de Negocio y Modelo Freemium:* Especificación del modelo comercial de DataMaq ($0 de por vida, Ciclo PRO de 60 días incluido en obras/consultorías, bifurcación Free entre Vitrina Pública Anonimizada de 30 días y Monitoreo Privado Básico de 14 días).

---

### 4. Analítica de Procesos — Diseño Conceptual (Exploratorio)

* 📄 [`docs/disponibilidad-maquina-diseno-conceptual.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/disponibilidad-maquina-diseno-conceptual.md)
  *Disponibilidad de Máquina a partir del Comportamiento Energético:* Documento de diseño conceptual sobre cómo inferir marcha / parada programada / parada no programada desde las variables eléctricas. Cubre certezas y dudas abiertas, segmentación modal de regímenes de potencia (binning logarítmico, persistencia topológica 1-D, barrido de ancho de banda, dinámica temporal |ΔP| y estacionariedad), calibración de umbrales marcha/parada, desagregación de cargas para medidores agregados (NILM: clustering por nivel vs. detección de eventos ΔP), comparación Reglas vs. ML supervisado, y el roadmap secuencial de implementación.

* 📄 [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md)
  *Desagregación de Cargas (NILM) sobre un Medidor Agregado:* Implementación del paso 4 del roadmap anterior. Cubre qué es y qué no es inferible a 300 s de cadencia (tabla por aparato), el catálogo genérico de `Carga`, las campañas de caracterización activa y pasiva que miden firmas reales poniendo el medidor en ráfaga sin tocar la cadencia permanente, la detección de escalones (ΔP, ΔQ) y su emparejado en episodios, la desambiguación por duración de cargas resistivas indistinguibles en potencia, el motor batch idempotente de atribución de kWh contra el contador acumulado, el residual `NO_ATRIBUIDO` como salida de primera clase, y el bucle de corrección humana que construye el dataset etiquetado.

* 📄 [`docs/asistente-conversacional-diseno.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/asistente-conversacional-diseno.md)
  *Asistente Conversacional (Chatbot) — Diseño Conceptual:* Chatbot dentro de la app que explica en lenguaje natural el estado de la planta del usuario logueado (telemetría, alertas, disponibilidad, cargas), con aislamiento multi-tenant estricto por `organizacion_id`. Restricción de partida: VPS sin GPU, por lo que la clasificación de intención corre local (embeddings en CPU) y la generación de texto se delega a Groq. Certezas, dudas abiertas y notas de implementación previas al diseño técnico cerrado.

---

## ⚡ Guías de Desarrollo Rápidas

* 📄 [`docs/entornos.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/entornos.md)
  *Entornos del proyecto:* rutas absolutas de cada entorno de desarrollo (laptop y PC de escritorio) y del entorno de producción (VPS vía `ssh vps`).
* Para el historial cronológico de cambios de la plataforma: [`CHANGELOG.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/CHANGELOG.md)
* Para convenciones de código, Clean Architecture y nomenclatura de DTOs: [`CONVENTIONS.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/CONVENTIONS.md)
* Para instrucciones de agentes y reglas de dependencias: [`AGENTS.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/AGENTS.md)
* Para puesta en marcha, scripts y catálogo de endpoints: [`README.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/README.md)
