# Índice Maestro de Documentación Técnica — Datamaq Telemetry

> **Repositorio:** `datamaq-telemetry` (Backend FastAPI, Ingestión MQTT y Motor de Analítica)  
> **Última Actualización:** 2026-08-23  
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
  - **Alertas e Incidentes:** `GET /api/alertas` y `PATCH /api/alertas/{id}/resolver`.
  - **Metrología 2-TI:** `PATCH /api/dispositivos/{id}` (`fases_con_ti`, `tipo_instalacion`).
  - **Topología Unifilar y Layout 2D:** `/api/v1/planta/unifilar` y `/api/v1/planta/layout`.

---

### 2. Protocolos de Hardware & Dispositivos IoT (Powermeter ESP32)

* 📄 [`docs/powermeter_mqtt_protocol.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/powermeter_mqtt_protocol.md)  
  *Protocolo MQTT:* Mapa completo de tópicos (`inst`, `acc`, `energyio`, `status`, `event`, `add`, `onoff`, `conf`), esquemas JSON (formatos compacto por fase y extendido), cadencia de publicación (300s estándar / ráfagas sub-minutales), QoS y perfiles de conexión.
* 📄 [`docs/provisioning_guide.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/provisioning_guide.md)  
  *Guía de Aprovisionamiento en Campo:* Procedimiento CLI (`scripts/provision_device.py`) e interfaz web local (`192.168.4.1`) para conectar medidores al servidor propio de Datamaq o restaurar al broker oficial de fábrica.
* 📄 [`docs/deteccion-anomalias-fases-y-polaridad.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/deteccion-anomalias-fases-y-polaridad.md)  
  *Detección de Anomalías Eléctricas:* Algoritmos matemáticos en dominio para detección automática de inversión de polaridad en transformadores de corriente (`TI_INVERTIDO`), cruce de fases (CT Mismatch) y orden de secuencia de fases ($R-S-T$ vs. $R-T-S$).

---

### 3. Modelo de Datos, Persistencia y Gobernanza

* 📄 [`docs/database_erd.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/database_erd.md)  
  *Diagrama Entidad-Relación (ERD):* Diagrama Mermaid autogenerado de todas las tablas MySQL, índices B-Tree, columnas de ingeniería y matriz de políticas de retención.
* 📄 [`docs/to_www-datamaq.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/to_www-datamaq.md)  
  *Directiva de Negocio y Modelo Freemium:* Especificación del modelo comercial de DataMaq ($0 de por vida, Ciclo PRO de 60 días incluido en obras/consultorías, bifurcación Free entre Vitrina Pública Anonimizada de 30 días y Monitoreo Privado Básico de 14 días).

---

## ⚡ Guías de Desarrollo Rápidas

* Para el historial cronológico de cambios de la plataforma: [`CHANGELOG.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/CHANGELOG.md)
* Para convenciones de código, Clean Architecture y nomenclatura de DTOs: [`CONVENTIONS.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/CONVENTIONS.md)
* Para instrucciones de agentes y reglas de dependencias: [`AGENTS.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/AGENTS.md)
* Para puesta en marcha, scripts y catálogo de endpoints: [`README.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/README.md)
