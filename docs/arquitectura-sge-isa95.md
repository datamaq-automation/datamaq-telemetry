# Arquitectura de Datos SGE e ISA-95 (Jerarquía de Activos y Topología)

> **Repositorio:** `datamaq-telemetry`  
> **Estándares:** ANSI/ISA-95.00.01-2010 (Enterprise-Control System Integration) / ISO 50001:2018 (Energy Management Systems)  
> **Patrón de Persistencia:** GitOps Declarativo en `./data/` + Time-Series en MySQL  
> **Estado:** Documento Canónico Vivo

---

## 1. Fundamentos: Convergencia ISA-95 e ISO 50001

En la industria moderna, la telemetría de energía no debe concebirse como una lista plana de dispositivos IoT, sino como un **modelo jerárquico de control y balance de energía**. 

Para estructurar la plataforma `datamaq-telemetry` de forma robusta y alineada con la ingeniería de planta, adoptamos los niveles de jerarquía del estándar **ANSI/ISA-95**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Nivel 4: Empresa / Corporativo (Enterprise / Multi-Tenant)               │
│ -> Organización (Razón Social, Plan Comercial, CUIT, Contacto)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│ Nivel 3: Sitio / Instalación (Site / Plant)                              │
│ -> Planta Física (Frontera del SGE ISO 50001, Georreferenciación, Metas)│
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│ Nivel 2: Área / Proceso (Area / Production Line / Electrical Node)       │
│ -> Nodos Unifilares: Transformador, TGBT, Subtableros, Cargas Clave     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│ Nivel 1: Unidad de Trabajo / Celda (Work Unit / Sensor IoT)             │
│ -> Dispositivo Powermeter (ESP32, MAC Address, TI R-S-T, Telemetría)     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Requisitos de ISO 50001 (Sistemas de Gestión de la Energía)

La norma **ISO 50001:2018** define requisitos concretos que se resuelven a través de este modelo:

1. **Límites y Alcance del SGE (Scope & Boundaries):**
   - Cada **Planta** define la frontera física y operativa del sistema de gestión.
   - Permite agregar consumos a nivel de acometida general para balances energéticos globales.
2. **Usos Significativos de la Energía (USE / SEU - Significant Energy Uses):**
   - En el unifilar, las cargas marcadas con `uso_significativo: true` reciben seguimiento prioritario.
   - Se tipifican por `categoria_uso` (ej. *PROCESO_PRODUCTIVO*, *CLIMATIZACION*, *AIRE_COMPRIMIDO*, *HORNOS*).
3. **Línea de Base Energética (EnB) e Indicadores de Desempeño (EnPI):**
   - Cada nodo o carga relevante puede declarar su `variable_relevante` (ej. *toneladas_producidas*, *ciclos_inyeccion*, *grados_dia*).
   - Permite normalizar el consumo en kWh respecto a la producción real.

---

## 3. Estructura Declarativa Multinivel en `./data/`

La persistencia de la jerarquía física y administrativa no reside en tablas rígidas de MySQL, sino en un esquema declarativo GitOps versionado en el sistema de archivos:

```text
data/
├── organizaciones.yml                     # [Nivel 1: Índice Maestro Corporativo]
└── organizaciones/
    └── {organizacion_id}/                 # Carpeta por Organización (Tenant)
        ├── organizacion.yml               # Atributos fiscales, planes y directivas
        └── plantas/
            └── {planta_id}/               # [Nivel 2: Sitio / Frontera SGE]
                ├── planta.yml             # Dirección, geo, metas globales SGE
                ├── unifilar.yml           # [Nivel 3: Topología Eléctrica e ISA-95]
                └── layout.yml             # [Nivel 3: Naves, Zonas y Coordenadas 2D]
```

### 3.1. Nivel 1: Organización (`organizacion.yml`)
Define la entidad legal y comercial:
```yaml
id: "acme-industrias"
nombre: "Acme Industrial S.A."
cuit: "30-98765432-1"
plan_id: "plan-pro"
modo_free: "PRIVADO_BASICO"
email_contacto: "energia@acme.com.ar"
```

### 3.2. Nivel 2: Planta (`planta.yml`)
Frontera física del SGE:
```yaml
id: "planta-pacheco"
nombre: "Planta Pacheco - Forja y Estampado"
direccion: "Ruta 9 Km 35, Tigre, Bs.As."
latitud: -34.4512
longitud: -58.6341
meta_sge:
  reduccion_consumo_pct: 5.0
  linea_base_ano: 2025
```

### 3.3. Nivel 3: Diagrama Unifilar (`unifilar.yml`)
Topología del árbol de potencia y clasificación de cargas:
```yaml
nodos:
  - id: "trafo-01"
    nombre: "Transformador 1 (13.2 kV / 380 V)"
    tipo: "TRANSFORMADOR"
    tension_nominal_v: 13200.0
    capacidad_nominal_kva: 1250.0

  - id: "tgbt-01"
    nombre: "Tablero General de Baja Tensión"
    tipo: "TGBT"
    padre_id: "trafo-01"
    tension_nominal_v: 380.0

  - id: "medidor-horno-1"
    nombre: "Horno de Inducción #1"
    tipo: "CARGA"
    padre_id: "tgbt-01"
    dispositivo_id: "dev-horno-01"
    tension_nominal_v: 380.0
    potencia_nominal_kw: 350.0
    uso_significativo: true
    categoria_uso: "PROCESO_PRODUCTIVO"
    variable_relevante: "toneladas_acero"
```

### 3.4. Nivel 3: Layout Espacial (`layout.yml`)
Mapeo visual en naves industriales:
```yaml
plano_svg_url: "/assets/plantas/pacheco_layout.svg"
zonas:
  - id: "nave-forja"
    nombre: "Nave Forja y Prensas"
    color: "#D9534F"
    coordenadas:
      x: 0.0
      y: 0.0
      ancho: 100.0
      alto: 60.0
dispositivos:
  - dispositivo_id: "dev-horno-01"
    zona_id: "nave-forja"
    posicion:
      x: 25.0
      y: 30.0
```

---

## 4. Ventajas Operativas y de Mantenimiento

1. **Aislamiento de Responsabilidades:** Mantenimiento eléctrico puede modificar `unifilar.yml` sin riesgo de alterar configuraciones de facturación de la organización.
2. **Historial de Cambios e Integridad:** Cada agregado de transformador o medidor queda registrado en Git (`git log`, PRs auditables).
3. **Compatibilidad hacia Atrás (Backward Compatibility):** `YamlOrganizacionesRepository` procesa tanto esquemas granulares por directorio como estructuras consolidadas.
4. **Validación Automática en Arranque:** La aplicación ejecuta en su `lifespan` el `verificador_consistencia_organizaciones` garantizando que los `organization_id` en las tablas MySQL correspondan siempre a entidades válidas del modelo declarativo.
