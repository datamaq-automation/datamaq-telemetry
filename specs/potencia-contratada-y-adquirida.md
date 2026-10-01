# Spec: Línea de potencia contratada y tracking de demanda cuarto-horaria

> **Estado:** en desarrollo · **Fecha:** 2026-10-01 · **Dueño:** agustin
> **Origen:** bloque `## Repo: datamaq-telemetry` de `specs/potencia-contratada-y-adquirida.md` del repo padre.
> **Decisiones aplicables:** `decisions/2026-10-01_potencia-contratada-y-adquirida-en-curso.md` (D1–D5),
> `decisions/2026-09-24_escala-fija-potencia-activa.md`, `decisions/2026-09-27_costo-estimado-periodo-en-curso.md`.
> **Repos afectados:** `datamaq-telemetry` (este bloque), `app-datamaq`.

## Repo: `datamaq-telemetry`

**Traspasada a hija:** sí (2026-10-01) · **Bloque cerrado:** no

### 1. Objetivo y Contexto

**Objetivo:** Exponer la potencia contratada del contrato y calcular la demanda máxima en bloques de 15 minutos en lo que va del período de facturación actual ("Potencia Adquirida en Curso").

**Alcance:**
- Permitir declarar `potencia_contratada_punta_kw` y `potencia_contratada_fuera_punta_kw` en `data/organizaciones.yml` bajo `nodos_unifilar[tipo=acometida]` (si solo se declara `potencia_contratada_kw`, se replica en ambas franjas).
- Exponer en `ResumenNodoUnifilarDTO` y/o endpoint de analítica de planta la estructura de demanda:
  - `potencia_contratada_punta_kw: float | None`
  - `potencia_contratada_fuera_punta_kw: float | None`
  - `potencia_adquirida_punta_en_curso_kw: float | None`
  - `potencia_adquirida_fuera_punta_en_curso_kw: float | None`
  - `ultima_potencia_adquirida_punta_kw: float | None` (de última factura)
  - `ultima_potencia_adquirida_fuera_punta_kw: float | None` (de última factura)
- Implementar caso de uso o servicio de dominio de cálculo de demanda máxima cuarto-horaria (bloques de 15 min reloj: :00, :15, :30, :45) sobre la acometida desde el inicio del período actual, segregando muestras según caigan en Horas Punta (18:00 a 23:00) o Fuera de Punta (resto).
- Conectar este cálculo con `ConsultarCostoEstimadoUseCase` para resolver el componente de potencia excedida en ambas franjas (`costo_potencia`).

**Fuera de alcance:**
- Tarifación horaria dinámica de energía (se mantiene promedio ponderado según D3 de decisión 2026-09-27).

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- Entidad `FacturaDistribuidora`: `src/domain/sge/entities.py`.
- Repositorio de organizaciones: `src/infrastructure/yaml/repositories/organizaciones_repository.py`.
- Caso de uso de costo estimado: `src/application/use_cases/consultar_costo_estimado.py`.
- No hay nada que borrar; se agregan campos y cálculos aditivos.

**Ya hecho por el padre (no repetir):**
- Decisiones formalizadas en `decisions/2026-10-01_potencia-contratada-y-adquirida-en-curso.md`.

---

### 2. Dominio & Puertos

1. **Entidad `NodoUnifilar` (`src/domain/telemetria/entities.py`):**
   - Incorpora campos opcionales:
     - `potencia_contratada_punta_kw: float | None = None`
     - `potencia_contratada_fuera_punta_kw: float | None = None`
   - Ambas magnitudes en kilovatios (kW), consistentes con `FacturaDistribuidora`.

2. **Entidad `FacturaDistribuidora` (`src/domain/sge/entities.py`):**
   - Property aditiva `valor_potencia_ars_kw_promedio: float | None`:
     - Determina el precio promedio $/kW cobrado en la factura de potencia.
     - Divide `importe_potencia_ars` por la potencia total facturada (suma de potencia contratada en punta y fuera de punta más las potencias excedidas liquidadas).
     - Si falta `importe_potencia_ars` o los kW base son 0/None, retorna `None`.

3. **Servicio de Dominio `CalculadorDemandaCuartohorariaService` (`src/domain/telemetria/servicios/calculador_demanda_cuartohoraria.py`):**
   - Dominio 100% puro (stdlib + `@dataclass(frozen=True)`).
   - Modelado de `DemandaCuartohoraria`:
     - `potencia_adquirida_punta_kw: float | None`
     - `potencia_adquirida_fuera_punta_kw: float | None`
     - `momento_pico_punta: datetime | None`
     - `momento_pico_fuera_punta: datetime | None`
     - `bloques_evaluados: int`
   - Segregación estricta por franja horaria argentina (`America/Argentina/Buenos_Aires`):
     - Horas Punta: bloques cuyo inicio en hora local cumpla `18 <= hora < 23` (18:00 a 22:59:59).
     - Fuera de Punta: resto del día (`hora < 18` o `hora >= 23`).
   - Bloques cuarto-horarios reloj: buckets de 900 segundos (:00, :15, :30, :45). La potencia en cada bloque es el promedio de potencia activa de las lecturas dentro del intervalo (expresada en kW = W / 1000).

---

### 3. Casos de Uso & DTOs

1. **`ResumenNodoUnifilarDTO` (`src/application/dtos/planta_estructura_dto.py`):**
   - Se agregan los siguientes campos en snake_case (alineados a las convenciones de `plantaUnifilar.ts` en frontend):
     - `potencia_contratada_punta_kw: float | None = None`
     - `potencia_contratada_fuera_punta_kw: float | None = None`
     - `potencia_adquirida_punta_en_curso_kw: float | None = None`
     - `potencia_adquirida_fuera_punta_en_curso_kw: float | None = None`
     - `ultima_potencia_adquirida_punta_kw: float | None = None`
     - `ultima_potencia_adquirida_fuera_punta_kw: float | None = None`

2. **`ConsultarNodoUnifilarUseCase` (`src/application/use_cases/consultar_nodo_unifilar.py`):**
   - En el método `resumen()`:
     - Resuelve la tríada de potencia:
       - **Contratada:** Si el nodo es `ACOMETIDA` (o tiene declarada contratada), lee `nodo.potencia_contratada_punta_kw` y `nodo.potencia_contratada_fuera_punta_kw`. Si están en `None`, aplica fallback (D4) a la última `FacturaDistribuidora` de la planta.
       - **Última Adquirida:** De la última `FacturaDistribuidora` cargada para la planta (`potencia_adquirida_punta_kw`, `potencia_adquirida_fuera_punta_kw`).
       - **Adquirida en Curso:** Para nodos acometida o con medidores frontera, calcula la demanda máxima en bloques de 15 minutos desde el inicio del período en curso (día 1 del mes a las 00:00 hora local) segregada en Punta y Fuera de Punta.

3. **`ConsultarCostoEstimadoUseCase` (`src/application/use_cases/consultar_costo_estimado.py`):**
   - Desbloquea el cálculo de `costo_potencia_ars`:
     - Consulta la última factura con componente de potencia (`tipo_dato == "potencia"` o con `importe_potencia_ars`).
     - Obtiene la potencia contratada (acometida con fallback a factura) y la demanda en curso calculada en bloques de 15 min.
     - Si no hay factura de potencia: `costo_potencia_ars = None`, `motivo_potencia_sin_dato = "tarifa_potencia_no_disponible"`.
     - Si hay factura pero no hay telemetría en curso: `costo_potencia_ars = None`, `motivo_potencia_sin_dato = "demanda_maxima_no_disponible"`.
     - Si están ambos:
       `cargo_base = (pot_contratada_punta + pot_contratada_fuera_punta) * tarifa_kw`
       `exceso_punta = max(0.0, demanda_en_curso_punta - pot_contratada_punta)`
       `exceso_fp = max(0.0, demanda_en_curso_fp - pot_contratada_fuera_punta)`
       `costo_potencia_ars = round(cargo_base + (exceso_punta + exceso_fp) * tarifa_kw, 2)`
       `motivo_potencia_sin_dato = None`.

4. **Repositorio YAML (`src/infrastructure/yaml/repositories/organizaciones_repository.py`):**
   - En `_parsear_nodo_unifilar`:
     - Lee `potencia_contratada_punta_kw` y `potencia_contratada_fuera_punta_kw`.
     - Si se define únicamente `potencia_contratada_kw`, replica el valor en ambas franjas.

---

### 4. Matriz de Pruebas (RED Suite)

- **`tests/unit/test_calculador_demanda_cuartohoraria.py`:**
  - Segregación horaria en franjas Punta (18:00 a 23:00) y Fuera de Punta (resto) en zona horaria de Buenos Aires.
  - Agrupación precisa en bloques reloj de 15 minutos (:00, :15, :30, :45).
  - Cálculo de demanda pico máxima en Punta y Fuera de Punta sobre lecturas agregadas.
  - Tolerancia y reporte de `None` si no hay datos en alguna de las franjas.
- **`tests/unit/test_nodo_unifilar_potencia_contratada.py`:**
  - Lectura YAML de `potencia_contratada_punta_kw` y `potencia_contratada_fuera_punta_kw`.
  - Replicación en ambas franjas cuando solo se define `potencia_contratada_kw`.
  - Exposición de la tríada completa en `ResumenNodoUnifilarDTO`.
  - Fallback a la última factura de la planta si la acometida no tiene declarada la potencia contratada en YAML.
- **`tests/unit/test_consultar_costo_estimado_uc.py`:**
  - Desbloqueo del cálculo de potencia: sin exceso (solo cargo contratada).
  - Con exceso de potencia en Punta y/o Fuera de Punta (cargo base + penalización).
  - Preservación de "s/d" con motivo explícito cuando falta factura de potencia o telemetría en curso.

---

### 5. Commits Atómicos

1. `docs: adoptar spec de potencia contratada y demanda cuarto-horaria`
2. `feat(domain): agregar potencia contratada a NodoUnifilar y calculador de demanda cuarto-horaria`
3. `feat(yaml): soporte de potencia contratada en organizaciones_repository y data/organizaciones.yml`
4. `feat(application): exponer triada de demanda en ResumenNodoUnifilarDTO y desbloquear costo de potencia en ConsultarCostoEstimadoUseCase`
5. `test: suite de pruebas unitarias para demanda cuarto-horaria, unifilar y costo estimado`

---

### 6. Criterios del Gauntlet

- [ ] Cobertura de tests unitarios mantenida o superando el umbral de 85% (`pytest tests/unit/`).
- [ ] Verificación estricta de tipos con `pyright` (0 errores, 0 advertencias).
- [ ] Linter y formateador `ruff check .` y `ruff format` sin violaciones.
- [ ] Integridad de `__init__.py` de 0 bytes.
- [ ] Clean Architecture y límites de tamaño de archivo/función validados (`verify_architecture.py` y `verify_code_size.py`).
- [ ] Suite completa de integración en verde (`tests/integration/`).
