# Spec: Desacoplamiento de Facturas Distribuidora y Liquidación MEM — Backend `datamaq-telemetry`

> **Estado:** cerrada · **Fecha:** 2026-10-02 · **Dueño:** Agustín  
> **Origen:** bloque `## Repo: datamaq-telemetry` de `specs/desacoplamiento-facturas-distribuidora-mem.md` del repo padre.  
> **Decisiones aplicables:** `decisions/2026-10-02_desacoplamiento-facturas-distribuidora-mem.md`, `decisions/2026-10-01_facturacion-integral-cammesa-mem.md`, `decisions/2026-09-28_energia-registrada-edelap.md`  
> **Repos afectados:** `datamaq-telemetry`, `datamaq-data`

## Repo: `datamaq-telemetry`

**Traspasada a hija:** sí (2026-10-02) · **Bloque cerrado:** sí

### 1. Objetivo y Contexto

**Objetivo:**
Completar el balance contable del parser de EDELAP (`ParserFacturaPotenciaEdelap`) extrayendo el subtotal neto de peaje y los impuestos/tasas provinciales y municipales (PBA Ley 11.769, Ley 11.969 y alumbrado público), para que ambos comprobantes (EDELAP y CAMMESA) cuenten con trazabilidad matemática al centavo (`neto + impuestos == total`).

**Alcance:**
- Modificar `ParserFacturaPotenciaEdelap` (`src/infrastructure/pdfplumber/parser_factura_distribuidora.py`):
  - Extraer `importe_neto_ars`: subtotal gravado y conceptos no gravados antes de impuestos (`SUBTOTAL POR SERVICIO ELECTRICO`).
  - Extraer `importe_impuestos_ars`: suma de `SUBTOTAL IMPUESTOS` (IVA 27%, Ley 11.769 Art. 74/75, Res. Gral. 3337/91) más `SUBTOTAL CARGOS VARIOS EXENTOS` (tasa de alumbrado municipal).
  - Asegurar invariante matemática: `importe_neto_ars + importe_impuestos_ars == importe_total_ars`.
- Mantener funciones y métodos bajo el umbral de 75 líneas (modularizando en helper privado `_extraer_importes_edelap`).
- Actualizar tests unitarios en `tests/unit/test_parser_factura_distribuidora.py` incorporando assertions contables y suite de los 12 PDFs reales de EDELAP.
- Regenerar los 12 períodos históricos de EDELAP en `data/facturas_distribuidora.yml` (repositorio `datamaq-data`) y validar con `test_verificador_facturas.py`.

**Fuera de alcance:**
- Modificar endpoints existentes o alterar contratos DTO (los campos `importe_neto_ars` e `importe_impuestos_ars` ya existen como opcionales en `FacturaDistribuidoraResponseDTO` y en la entidad `FacturaDistribuidora`).
- Modificar el cálculo de costo estimado en vivo (ya utiliza la tarifa integral de CAMMESA y potencia de EDELAP).

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- `src/domain/sge/entities.py:121-122`: `importe_neto_ars` e `importe_impuestos_ars` ya están definidos en la entidad `FacturaDistribuidora`.
- `src/application/dtos/sge_dto.py:FacturaDistribuidoraResponseDTO`: ya expone `importe_neto_ars` e `importe_impuestos_ars`.
- `src/application/mappers/sge_mapper.py:factura_to_dto`: ya mapea ambos importes directamente a partir de la entidad.
- `src/infrastructure/yaml/repositories/organizaciones_repository.py`: ya deserializa ambos campos opcionales del YAML.
- `src/infrastructure/yaml/verificador_facturas.py`: ya incluye ambos campos en el esquema de validación.
- `data/Papelera platense - EDELAP/*.pdf`: existen 12 facturas reales correspondientes a 2023-12 hasta 2024-11 con balance contable verificado al centavo.

**Ya hecho por el padre (no repetir):**
- Decisión de arquitectura registrada en `decisions/2026-10-02_desacoplamiento-facturas-distribuidora-mem.md`.

---

### 2. Dominio & Puertos

- **Entidad `FacturaDistribuidora` (`src/domain/sge/entities.py`):**
  - No requiere modificaciones estructurales. Ya contiene:
    - `importe_neto_ars: float | None = None`
    - `importe_impuestos_ars: float | None = None`
  - Invariante contable esperada para facturas con desglose completo:
    `importe_neto_ars + importe_impuestos_ars == importe_total_ars`.
- **Puerto `ParserFacturaDistribuidoraPort` (`src/domain/sge/ports.py`):**
  - Contrato `parsear(ruta_pdf: str, planta_id: str) -> FacturaDistribuidora` sin alteraciones.

---

### 3. Casos de Uso & DTOs

- **DTOs (`src/application/dtos/sge_dto.py`):**
  - `FacturaDistribuidoraResponseDTO` mantiene su contrato retrocompatible con `importe_neto_ars` e `importe_impuestos_ars` opcionales poblados para EDELAP.
- **Mappers (`src/application/mappers/sge_mapper.py`):**
  - `factura_to_dto` transfiere directamente los nuevos valores hacia la respuesta API.
- **Casos de Uso (`src/application/use_cases/consultar_facturas_distribuidora.py`):**
  - Sin cambios necesarios; entrega las entidades leídas desde el repositorio YAML.

---

### 4. Matriz de Pruebas (RED Suite)

1. **Tests Unitarios de Fixtures Sintéticos (`tests/unit/test_parser_factura_distribuidora.py`):**
   - `test_edelap_factura_202411_extrae_campos_reales`:
     - Assertions de `importe_neto_ars == 15419479.84`.
     - Assertions de `importe_impuestos_ars == 5612256.94`.
     - Invariante `importe_neto_ars + importe_impuestos_ars == importe_total_ars` (21.031.736,78).
   - `test_edelap_factura_202312_confirma_layout_estable_entre_periodos`:
     - Assertions de `importe_neto_ars == 3820806.65`.
     - Assertions de `importe_impuestos_ars == 1387528.61`.
     - Invariante `importe_neto_ars + importe_impuestos_ars == importe_total_ars` (5.208.335,26).
   - `test_edelap_factura_202402_sin_exceso_usa_demanda_registrada`:
     - Assertions de `importe_neto_ars == 3158192.35`.
     - Assertions de `importe_impuestos_ars == 1166980.82`.
     - Invariante `importe_neto_ars + importe_impuestos_ars == importe_total_ars` (4.325.173,17).

2. **Suite de 12 Facturas Reales de EDELAP (`tests/unit/test_parser_factura_distribuidora.py`):**
   - `test_edelap_12_facturas_reales_extraen_desglose_y_balancean`:
     - Itera sobre los 12 PDFs en `data/Papelera platense - EDELAP/*.pdf`.
     - Verifica que `importe_neto_ars` e `importe_impuestos_ars` no sean `None` y sean mayores a cero.
     - Verifica la cuadratura contable exacta: `importe_neto_ars + importe_impuestos_ars == pytest.approx(importe_total_ars, abs=1.0)`.

3. **Verificación de Integridad YAML (`tests/unit/test_verificador_facturas.py`):**
   - Valida la carga y consistencia del archivo `data/facturas_distribuidora.yml` con los 12 períodos de EDELAP regenerados.

---

### 5. Desglose de Commits Atómicos Planificados

1. **Commit 1 (RED):**
   `test(sge): assertions de balance contable (neto e impuestos) en facturas EDELAP`
   - Incorporación de aserciones de `importe_neto_ars`, `importe_impuestos_ars` y balance total en tests de EDELAP existentes y nuevo test de 12 facturas reales.
2. **Commit 2 (GREEN):**
   `feat(sge): extraccion de subtotal neto e impuestos en ParserFacturaPotenciaEdelap`
   - Extracción de `SUBTOTAL POR SERVICIO ELECTRICO`, `SUBTOTAL IMPUESTOS` y `SUBTOTAL CARGOS VARIOS EXENTOS` en `ParserFacturaPotenciaEdelap` respetando el límite de 75 líneas por función.
3. **Commit 3 (Data):**
   `fix(data): regeneracion de facturas historicas EDELAP con balance contable`
   - Regeneración de los 12 períodos de EDELAP en `data/facturas_distribuidora.yml` dentro del repositorio anidado `data/` (`datamaq-data`).
4. **Commit 4 (Docs):**
   `docs(sge): spec cerrada para desacoplamiento en backend telemetry`
   - Especificación completa y cerrada en `specs/desacoplamiento-facturas-distribuidora-mem.md`.

---

### 6. Criterios del Gauntlet

- `./scripts/pre-push.sh` pasa al 100%:
  - Etapa 1: Integridad (`__init__.py` de 0 bytes, arquitectura Clean/DIP, límites de tamaño).
  - Etapa 2: Ruff check y format sin violaciones.
  - Etapa 3: Pyright estricto en `src/` (0 errores de tipado).
  - Etapa 4: Pytest unitario completo con cobertura >= 85%.
