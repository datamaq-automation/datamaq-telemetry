# Directiva de Negocio y Especificación para `www-datamaq`

> **Origen:** `datamaq-telemetry` (Backend SSOT & Domain Engine)  
> **Destino:** `www-datamaq` (Web Pública, Catálogo de Planes, Pricing y Documentación SRS)  
> **Fecha:** 2026-08-23  
> **Estado:** Aprobado por el CEO / Titular  

---

## 1. Contexto Estratégico y Alineación del Modelo

El modelo de negocio de DataMaq se basa en la **instalación de medidores de energía Powermeter** y en la **consultoría técnica de optimización energética (demanda, potencia contratada y $\cos \varphi$)**.

* **El SaaS no es una vía de ingreso directo:** La plataforma de telemetría web en la nube se ofrece **sin costo recurrente de licencia ($0 de por vida)**. Actúa como diferenciador competitivo, vitrina de captación de clientes (*growth loop*) y canal de retención técnica.
* **Monetización real:** Mano de obra calificada en tableros (Obra Llave en Mano con margen +10%), Consultoría de Eficiencia Energética (+10%) e Integraciones a sistemas ERP (Xubio).

---

## 2. Definición del Ciclo de Vida PRO (60 días)

### 2.1 Activación por Instalación Inicial
* Toda nueva obra de instalación de medidores Powermeter (*SmartPlus*, *Gateway*, *Automate*) incluye **60 días (2 meses)** de **Versión PRO** completa de la plataforma:
  * 100% privado y confidencial.
  * Máxima resolución de telemetría (segundo a segundo / curvas de potencia cada 15 minutos).
  * Alertas críticas instantáneas por WhatsApp y Email (picos de potencia, desbalance, caída de $\cos \varphi$).
  * Retención de datos históricos por 365 días.
  * Diagnóstico profundo de transitorios y armónicos.
* **Fundamento comercial (Visión CEO):** 60 días cubre exactamente **2 ciclos completos de facturación de Edenor**. En el mes 1 el cliente ve su línea de base y en el mes 2 comprueba el ahorro real en su factura eléctrica, cerrando el ciclo de *Payback en 30 a 60 días*.

### 2.2 Extensión por Consultoría (Regla No Acumulable)
* Cada contratación de un servicio de consultoría energética (ajuste de potencia contratada, eliminación de penalidades $\cos \varphi$, auditoría estacional) **garantiza 60 días de Versión PRO a partir de la fecha de realización del servicio**.
* **Regla de No Acumulabilidad:** No se apilan períodos (ej: dos servicios en el mismo mes fijan la vigencia a 60 días desde la última fecha, no 120 días).

---

## 3. Bifurcación del Modelo Gratuito Post-PRO ($0 de por vida)

Al expirar los 60 días de la versión PRO sin una nueva consultoría, el cliente continúa accediendo a la plataforma sin costo mensual, pudiendo elegir entre dos modalidades:

### Opción A — Vitrina Pública Anonimizada (Opt-in)
* **Propuesta:** El cliente mantiene la **máxima resolución y curvas en tiempo real** a cambio de autorizar la publicación anónima de sus mediciones en la vitrina pública de DataMaq.
* **Garantía de Anonimización:** Cero datos de empresa (se omiten razón social, CUIT, marcas comerciales y ubicación exacta; solo se categoriza por rubro general, ej: *"Planta Metalmecánica - GBA Norte"*).
* **Retención:** 30 días de historial.
* **Beneficio para DataMaq:** Alimenta la vitrina comercial con curvas de carga industriales vivas y reales.

### Opción B — Monitoreo Privado Básico (Por Defecto)
* **Propuesta:** Los datos se mantienen **100% privados y confidenciales**, pero con resolución agregada para monitoreo general.
* **Granularidad:** Resúmenes agregados horarios y diarios (no curvas sub-minutales).
* **Retención:** 14 días de historial.
* **Alertas:** Resumen semanal por email (sin alertas de micro-eventos por WhatsApp).
* **Efecto Comercial ("Gatillo de Consultoría"):** Cuando el cliente detecta un desvío o pico en su factura de luz, la baja resolución le indica que hubo un evento pero requiere la consultoría de DataMaq para hacer el diagnóstico fino y reactivar los 60 días de PRO.

---

## 4. Modificaciones Concretas a Realizar en `www-datamaq`

### 4.1 Documentación SRS (`docs/srs.md`)
* Actualizar la **Sección 1.2 (Trinomio de Valor)** y **Sección 3.1 (Política de Precios)**:
  * Incorporar la cláusula de **60 días PRO incluidos con la instalación**.
  * Registrar la extensión de **60 días PRO por consultoría (no acumulable)**.
  * Documentar la bifurcación Free: **Vitrina Pública Anonimizada** vs. **Privado Básico Agregado**.

### 4.2 Backlog y Roadmap (`docs/todo.md`)
* Registrar la **Certeza Consolidada C-09**:
  * `C-09 | Ciclo PRO 60d + Free Bifurcado | 60 días PRO por instalación/consultoría (no acumulables). Al vencer: Free Privado Básico (default) o Vitrina Anónima.`
* Marcar como resuelto el dilema `[P-04] Modelo de Retención Post-Instalación`.

### 4.3 Catálogo de Planes (`data/content/planes.yaml`)
* **`plataforma-cloud`:**
  * Tagline: *"Plataforma web de telemetría y dashboard en tiempo real sin canon mensual. Incluye 60 días de Versión PRO con cada obra o consultoría."*
  * Bullets:
    - `"SaaS en la nube sin costo recurrente de licencia ($0 de por vida)"`
    - `"60 días de Versión PRO completa incluidos con la instalación de tus medidores"`
    - `"Cada consultoría energética renueva 60 días de Versión PRO"`
    - `"Al vencer: elegí entre aportar a la Vitrina Pública Anónima o mantener monitoreo privado horario"`
    - `"Compatible con toda la suite Powermeter (SmartPlus, Gateway, Automate)"`
* **`instalacion-hardware`:**
  * Bullets:
    - Agregar: `"Incluye 60 días de Plataforma PRO (curvas segundo a segundo, alertas WhatsApp y privacidad total)"`
* **`consultoria-energia`:**
  * Bullets:
    - Agregar: `"Garantiza 60 días de extensión de Plataforma PRO completa"`

### 4.4 Preguntas Frecuentes (`data/content/home_sections.yaml`)
* Añadir/Actualizar FAQ:
  * **Pregunta:** *"¿Qué sucede con la plataforma de telemetría después de los primeros 60 días?"*
  * **Respuesta:** *"La plataforma sigue siendo 100% gratuita ($0 de por vida). Podés elegir mantener la máxima resolución de datos donando tus mediciones de forma totalmente anónima a nuestra vitrina pública, o conservar tus datos 100% privados con resúmenes diarios y horarios. Además, cada nueva consultoría o auditoría técnica reactiva automáticamente 60 días de la versión PRO completa."*
