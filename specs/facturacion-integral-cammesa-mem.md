# Spec: Facturación Integral CAMMESA (MEM) y Desglose Regulatorio

> **Estado:** en desarrollo · **Fecha:** 2026-10-01 · **Dueño:** Agustín
> **Origen:** bloque `## Repo: datamaq-telemetry` de `specs/facturacion-integral-cammesa-mem.md` del repo padre.
> **Decisiones aplicables:** `decisions/2026-10-01_facturacion-integral-cammesa-mem.md`, `decisions/2026-09-24_factura-distribuidora-yaml.md`, `decisions/2026-09-28_energia-registrada-edelap.md`.
> **Repos afectados:** `datamaq-telemetry` (este bloque), `app-datamaq`.

## Repo: `datamaq-telemetry`

**Traspasada a hija:** sí (2026-10-01) · **Bloque cerrado:** no

### 1. Objetivo y Contexto

**Objetivo:**
Evolucionar el parser de CAMMESA, el modelo de dominio y los casos de uso en `datamaq-telemetry` para extraer y persistir el desglose regulatorio completo de la liquidación del MEM (potencia MEM, adicionales del MEM, transporte, MATER e impuestos), permitiendo calcular tanto la tarifa spot monómica como la tarifa integral de energía, y reflejar el costo estimado real en el SGE.

**Alcance:**
- Extender la entidad `FacturaDistribuidora` (`src/domain/sge/entities.py`) con los campos mayoristas:
  - `potencia_adquirida_mem_kw: float | None` (MW facturados x 1000).
  - `importe_potencia_mem_ars: float | None` (Subtotal cargos de potencia MEM).
  - `importe_adicionales_mem_ars: float | None` (Cargos adicionales del MEM).
  - `importe_transporte_mem_ars: float | None` (Subtotal cargos por transporte SADI / troncal).
  - `importe_otros_cargos_mem_ars: float | None` (Comercialización, administración, MATER Res. 281 y actividad de mercado).
  - `importe_neto_ars: float | None` (Subtotal antes de impuestos).
  - `importe_impuestos_ars: float | None` (IVA 27%, IVA perc. 3%, FNEE Ley 24065).
  - Propiedad de dominio `valor_energia_integral_ars_kwh: float | None` (costo neto total MEM / kWh).
- Evolucionar `ParserFacturaEnergiaCammesa` (`src/infrastructure/pdfplumber/parser_factura_distribuidora.py`):
  - Robustecer la regex de MWh y MW para soportar miles (`^[\d.]+,\d{2,3}$`).
  - Extraer sistemáticamente los renglones de Cargos de Potencia, Cargos Adicionales del MEM, Cargos por Transporte, Otros Cargos (Res. 281 + Actividad de Mercado), Subtotal Neto e Impuestos utilizando coordenadas verticales `_fila()`.
- Actualizar `FacturaDistribuidoraResponseDTO` (`src/application/dtos/sge_dto.py`) y `factura_to_dto` (`src/application/mappers/sge_mapper.py`).
- Ajustar `ConsultarCostoEstimadoUseCase` (`src/application/use_cases/consultar_costo_estimado.py`) para utilizar la tarifa integral de energía (`valor_energia_integral_ars_kwh` con fallback a `valor_energia_ars_kwh_promedio`).
- Actualizar el repositorio YAML (`src/infrastructure/yaml/repositories/organizaciones_repository.py`), el verificador de facturas (`src/infrastructure/yaml/verificador_facturas.py`) y el script de importación (`scripts/importar_factura_distribuidora.py`).
- Regenerar `data/facturas_distribuidora.yml` con el desglose completo de los 12 períodos de CAMMESA.
- Tests unitarios completos en `tests/unit/test_factura_distribuidora.py`, `tests/unit/test_parser_factura_distribuidora.py` y `tests/unit/test_consultar_costo_estimado_uc.py`.

**Fuera de alcance:**
- Cambios en interfaz web (`app-datamaq`): se desarrollarán en la sesión del frontend sobre este contrato de datos.

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- Parser: `src/infrastructure/pdfplumber/parser_factura_distribuidora.py:238-323`.
- Entidad: `src/domain/sge/entities.py:89-169`.
- DTO: `src/application/dtos/sge_dto.py:FacturaDistribuidoraResponseDTO`.
- Mappers: `src/application/mappers/sge_mapper.py:factura_to_dto`.
- Caso de uso: `src/application/use_cases/consultar_costo_estimado.py:57-84`.
- Repositorio y validador YAML: `src/infrastructure/yaml/verificador_facturas.py` y `src/infrastructure/yaml/repositories/organizaciones_repository.py`.
- PDFs reales: `data/Papelera platense - CAMMESA/*.pdf` (12 archivos verificados).

---

### 2. Dominio & Puertos

1. **Entidad `FacturaDistribuidora` (`src/domain/sge/entities.py`):**
   - Incorpora campos opcionales con valor por defecto `None`:
     - `potencia_adquirida_mem_kw: float | None = None`
     - `importe_potencia_mem_ars: float | None = None`
     - `importe_adicionales_mem_ars: float | None = None`
     - `importe_transporte_mem_ars: float | None = None`
     - `importe_otros_cargos_mem_ars: float | None = None`
     - `importe_neto_ars: float | None = None`
     - `importe_impuestos_ars: float | None = None`
   - Incorpora la propiedad calculada:
     ```python
     @property
     def valor_energia_integral_ars_kwh(self) -> float | None:
         """Tarifa integral neta del MEM ($/kWh) incluyendo potencia, adicionales y transporte."""
         if not self.energia_facturada_kwh or not self.importe_neto_ars or self.energia_facturada_kwh <= 0:
             return None
         return self.importe_neto_ars / self.energia_facturada_kwh
     ```
   - Mantiene la propiedad `valor_energia_ars_kwh_promedio` existente (tarifa spot monómica pura: `importe_energia_ars / energia_facturada_kwh`).
   - Mantiene pureza absoluta de dominio: sin librerías de terceros, inmutable (`@dataclass(frozen=True)`).

2. **Puertos:**
   - `ParserFacturaDistribuidoraPort` en `src/domain/sge/ports.py` mantiene su firma intacta: `parsear(ruta_pdf: str, planta_id: str) -> FacturaDistribuidora`.

---

### 3. Casos de Uso & DTOs

1. **DTO `FacturaDistribuidoraResponseDTO` (`src/application/dtos/sge_dto.py`):**
   - Agrega los campos:
     - `potencia_adquirida_mem_kw: float | None = Field(default=None, validation_alias="potenciaAdquiridaMemKw", serialization_alias="potenciaAdquiridaMemKw")`
     - `importe_potencia_mem_ars: float | None = Field(default=None, validation_alias="importePotenciaMemArs", serialization_alias="importePotenciaMemArs")`
     - `importe_adicionales_mem_ars: float | None = Field(default=None, validation_alias="importeAdicionalesMemArs", serialization_alias="importeAdicionalesMemArs")`
     - `importe_transporte_mem_ars: float | None = Field(default=None, validation_alias="importeTransporteMemArs", serialization_alias="importeTransporteMemArs")`
     - `importe_otros_cargos_mem_ars: float | None = Field(default=None, validation_alias="importeOtrosCargosMemArs", serialization_alias="importeOtrosCargosMemArs")`
     - `importe_neto_ars: float | None = Field(default=None, validation_alias="importeNetoArs", serialization_alias="importeNetoArs")`
     - `importe_impuestos_ars: float | None = Field(default=None, validation_alias="importeImpuestosArs", serialization_alias="importeImpuestosArs")`
     - `valor_energia_integral_ars_kwh: float | None = Field(default=None, validation_alias="valorEnergiaIntegralArsKwh", serialization_alias="valorEnergiaIntegralArsKwh")`

2. **Mapper `factura_to_dto` (`src/application/mappers/sge_mapper.py`):**
   - Mapea explícitamente cada uno de los nuevos campos desde la entidad al DTO.

3. **Caso de Uso `ConsultarCostoEstimadoUseCase` (`src/application/use_cases/consultar_costo_estimado.py`):**
   - Resuelve el valor unitario de energía priorizando la tarifa integral neta del MEM:
     ```python
     valor_kwh = (
         factura_energia.valor_energia_integral_ars_kwh
         if factura_energia and factura_energia.valor_energia_integral_ars_kwh is not None
         else (factura_energia.valor_energia_ars_kwh_promedio if factura_energia else None)
     )
     ```
   - De esta forma, el costo proyectado de energía del período en curso refleja fielmente la tarifa integral del MEM (~$74,93/kWh) en vez de la tarifa monómica spot pura (~$10,36/kWh).

---

### 4. Matriz de Pruebas (RED Suite)

1. **Dominio (`tests/unit/test_factura_distribuidora.py`):**
   - Test de inicialización de campos MEM en `FacturaDistribuidora`.
   - Test de cálculo de `valor_energia_integral_ars_kwh` cuando `importe_neto_ars` y `energia_facturada_kwh` están presentes.
   - Test de retorno `None` cuando falta `importe_neto_ars` o la energía es 0 o `None`.
   - Test de coexistencia de `valor_energia_ars_kwh_promedio` y `valor_energia_integral_ars_kwh`.

2. **Infraestructura (`tests/unit/test_parser_factura_distribuidora.py`):**
   - Test unitario sintético con palabras reales de CAMMESA simuladas.
   - Test con los 12 PDFs reales de CAMMESA (`data/Papelera platense - CAMMESA/*.pdf`):
     - Verifica que para cada factura se extrae `potencia_adquirida_mem_kw`, `importe_potencia_mem_ars`, `importe_adicionales_mem_ars`, `importe_transporte_mem_ars`, `importe_neto_ars`, `importe_impuestos_ars` e `importe_total_ars`.
     - Verifica que la suma de partidas (`importe_energia_ars + importe_potencia_mem_ars + importe_adicionales_mem_ars + importe_transporte_mem_ars + importe_otros_cargos_mem_ars`) cuadra exactamente con `importe_neto_ars` (tolerancia < 1.0 ARS).
     - Verifica que `importe_neto_ars + importe_impuestos_ars` cuadra con `importe_total_ars` (tolerancia < 1.0 ARS).

3. **Aplicación (`tests/unit/test_consultar_costo_estimado_uc.py`):**
   - Test que verifica que `costo_energia_ars` se calcula usando `valor_energia_integral_ars_kwh` de la factura de energía cuando está disponible.
   - Test que verifica fallback a `valor_energia_ars_kwh_promedio` cuando la factura de energía solo tiene tarifa monómica.

4. **Verificación e Integridad YAML (`tests/unit/test_verificador_facturas.py`):**
   - Test de parseo de los nuevos campos desde el archivo `data/facturas_distribuidora.yml`.

---

### 5. Desglose de Commits Atómicos Planificados

1. **Commit 1 (Dominio):**
   `feat(dominio): extender FacturaDistribuidora con desglose regulatorio MEM y tarifa integral`
   - Modificaciones en `src/domain/sge/entities.py`.
   - Tests en `tests/unit/test_factura_distribuidora.py`.

2. **Commit 2 (Infraestructura / Parser):**
   `feat(infra): extraer desglose regulatorio completo en ParserFacturaEnergiaCammesa`
   - Modificaciones en `src/infrastructure/pdfplumber/parser_factura_distribuidora.py`.
   - Modificaciones en `src/infrastructure/yaml/repositories/organizaciones_repository.py`.
   - Modificaciones en `scripts/importar_factura_distribuidora.py`.
   - Tests en `tests/unit/test_parser_factura_distribuidora.py`.

3. **Commit 3 (Aplicación):**
   `feat(aplicacion): exponer desglose MEM en DTOs y usar tarifa integral en costo estimado`
   - Modificaciones en `src/application/dtos/sge_dto.py`.
   - Modificaciones en `src/application/mappers/sge_mapper.py`.
   - Modificaciones en `src/application/use_cases/consultar_costo_estimado.py`.
   - Tests en `tests/unit/test_consultar_costo_estimado_uc.py`.

4. **Commit 4 (Datos):**
   `feat(datos): regenerar facturas_distribuidora.yml con desglose completo de CAMMESA`
   - Regeneración de `data/facturas_distribuidora.yml` para los 12 períodos de CAMMESA.
   - Ejecución de `scripts/verificar_facturas.py` y validación completa del Gauntlet.

---

### 6. Criterios del Gauntlet

- `./scripts/pre-push.sh` pasa al 100%:
  - Etapa 1: Integridad (`__init__.py` de 0 bytes, arquitectura, tamaño).
  - Etapa 2: Ruff check & format sin errores.
  - Etapa 3: Pyright en modo estricto en `src/` (0 errores).
  - Etapa 4: Pytest unitario completo con cobertura >= 85%.
