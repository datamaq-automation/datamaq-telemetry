# Spec: Dimensionador de Bancos de Capacitores — Período Histórico 30 Días

**Bloque Backend (`datamaq-telemetry`)**  
**Origen:** [`../specs/dimensionador-30d.md`](../specs/dimensionador-30d.md)

---

## 1. Objetivo y Contexto

**Responsabilidad:** Reemplazar cálculos simulados del endpoint `/banco-capacitores/planta` con consulta real de histórico de 30 días. Exponer `periodo_dias` como parámetro en `/nodo/unifilar/{nodo_id}` para que frontend pueda solicitar ventanas distintas.

### Estado Actual

- `ConsultarAnaliticaPlantaUseCase.obtener_banco_capacitores(planta_id, periodo_dias=7)` ignora tanto `planta_id` como `periodo_dias`, retorna P=120 kW, FP=0.88 (hardcodeados).
- `/nodo/unifilar/{nodo_id}` expone `compensacion_historica` con cálculo correcto, pero sin query param para variar `periodo_dias` (fijo a 7).
- `DimensionadorCompensacionService.calcular_potencia_compensacion()` ya recibe `q_reactiva_kvar` (commit 88c60a0) y descarta sobrecompensación correctamente.

---

## 2. Dominio & Puertos

**a) Servicios de Dominio**

- `DimensionadorCompensacionService.calcular_potencia_compensacion()` — ya implementado, reutilizar.
- `ConsultarTelemetriaUseCase` — reutilizar para extraer P, Q, FP históricos con `periodo_dias` variable.

**b) DTOs Nuevos o Modificados**

- `AnaliticaBancoCapacitoresPlantaDTO`:
  ```python
  class AnaliticaBancoCapacitoresPlantaDTO:
      planta_id: str
      periodo_dias: int
      potencia_activa_promedio_kw: float | None
      potencia_reactiva_promedio_kvar: float | None
      potencia_reactiva_max_kvar: float | None
      factor_potencia_promedio: float | None
      fp_objetivo: float
      qc_necesaria_kvar: float | None
      banco_comercial_sugerido_kvar: float | None
      escalones_sugeridos_kvar: list[float]
      sobrecompensacion_sostenida: bool  # NEW: Q_max <= 0
      fecha_calculo: datetime
  ```

- `CompensacionHistoricaDTO` — ya existe, agregar `sobrecompensacion_sostenida: bool`.

**c) Casos de Uso (Use Cases)**

- `ConsultarAnaliticaPlantaUseCase.obtener_banco_capacitores(planta_id, periodo_dias=30)`:
  1. Llamar `ConsultarTelemetriaUseCase` con `planta_id`, `periodo_dias * 24` horas.
  2. Extraer series de P, Q, FP (igual que en `_calcular_compensacion_historica`).
  3. Promediar P, Q, FP; calcular Q_max, Q_min.
  4. Llamar `DimensionadorCompensacionService.calcular_potencia_compensacion(p, fp, q_prom)`.
  5. Retornar `sobrecompensacion_sostenida = Q_max <= 0.0`.

- `ConsultarNodoUnifilarUseCase`:
  - Agregar parámetro `periodo_dias: int = 30` a `resumen()`.
  - Pasar a `_calcular_compensacion_historica(nodo, dispositivos_ids, periodo_dias=periodo_dias)`.

**d) Rutas FastAPI**

- `GET /nodo/unifilar/{nodo_id}?periodo_dias=30` — parámetro query nuevo.
- `GET /banco-capacitores/planta?planta_id=X&periodo_dias=30` — parámetro query nuevo, ruta existente pero lógica nueva.

---

## 3. Casos de Uso & DTOs

### `ConsultarAnaliticaPlantaUseCase.obtener_banco_capacitores(planta_id, periodo_dias=30)`

**Entrada:**
```python
planta_id: str
periodo_dias: int = 30
```

**Salida:**
```python
AnaliticaBancoCapacitoresPlantaDTO(
    planta_id=planta_id,
    periodo_dias=periodo_dias,
    potencia_activa_promedio_kw=120.5,
    potencia_reactiva_promedio_kvar=45.3,
    potencia_reactiva_max_kvar=220.7,
    factor_potencia_promedio=0.94,
    fp_objetivo=0.96,
    qc_necesaria_kvar=5.2,
    banco_comercial_sugerido_kvar=7.5,
    escalones_sugeridos_kvar=[2.5, 5.0, 7.5],
    sobrecompensacion_sostenida=False,  # Q_max > 0
    fecha_calculo=datetime.now(timezone.utc),
)
```

**Flujo:**
1. Validar `planta_id`, `periodo_dias > 0 && <= 60`.
2. Consultar puntos de telemetría últimos `periodo_dias * 24` horas (reutilizar `ConsultarTelemetriaUseCase`).
3. Extraer listas de P, Q, FP (mismo código que `_calcular_compensacion_historica`).
4. Si vacío → retornar DTO con Nones.
5. Promediar: `p_prom = sum(p_vals) / len(p_vals)`, `q_prom = sum(q_vals) / len(q_vals)`, etc.
6. `q_max = max(q_vals)`, `sobrecompensacion_sostenida = q_max <= 0.0`.
7. Llamar `DimensionadorCompensacionService.calcular_potencia_compensacion(p_prom, fp_prom, q_prom)`.
8. Si `qc_calc > 0` → sugerir banco comercial; si no → `banco_sugerido = None`.

### `ConsultarNodoUnifilarUseCase.resumen(..., periodo_dias=30)`

**Cambios:**
- Firma: agregar parámetro `periodo_dias: int = 30`.
- `resumen()` → pasar a `_calcular_compensacion_historica()`.
- Ruta FastAPI: exponer `?periodo_dias=30` como query param (default 30, antes 7).

---

## 4. Matriz de Pruebas

### Unitarias (`test_analitica_banco_capacitores.py`)

```python
def test_obtener_banco_capacitores_consulta_real():
    """Valida que obtener_banco_capacitores() consulta histórico, no retorna hardcodeados."""
    # Setup: planta con histórico de 30 días, P=100 kW, Q=50 kVAr promedio
    # Action: obtener_banco_capacitores(planta_id, periodo_dias=30)
    # Assert: potencia_activa_promedio_kw ≈ 100, no 120 (hardcodeado anterior)

def test_obtener_banco_capacitores_sobrecompensado():
    """Si Q_max <= 0, retorna sobrecompensacion_sostenida=True, banco_sugerido=None."""
    # Setup: planta con Q siempre negativo (Q_max=-10)
    # Assert: sobrecompensacion_sostenida=True, banco_sugerido=None

def test_obtener_banco_capacitores_periodo_dias_variable():
    """periodo_dias parámetro se respeta en la consulta."""
    # Setup: planta con histórico de 60 días
    # Action: obtener_banco_capacitores(planta_id, periodo_dias=7) vs periodo_dias=30
    # Assert: P, Q, FP difieran según la ventana (7 días vs 30 días)

def test_obtener_banco_capacitores_sin_datos():
    """Si sin histórico, retorna DTOs con Nones."""
    # Setup: planta sin puntos de telemetría en período
    # Action: obtener_banco_capacitores(planta_id, periodo_dias=30)
    # Assert: potencia_activa_promedio_kw=None, banco_sugerido=None
```

### Integración (`test_consultar_analitica_planta.py`)

```python
def test_endpoint_banco_capacitores_planta_retorna_reales():
    """GET /banco-capacitores/planta retorna P, Q, FP reales."""
    # Setup: POST telemetría fixture para planta de test
    # Action: GET /banco-capacitores/planta?planta_id=test-planta&periodo_dias=30
    # Assert: response.potencia_activa_promedio_kw no es 120 (hardcodeado anterior)

def test_endpoint_nodo_unifilar_expone_periodo_dias():
    """GET /nodo/unifilar/{nodo_id}?periodo_dias=30 acepta query param."""
    # Setup: nodo existente
    # Action: GET /nodo/unifilar/{nodo_id}?periodo_dias=30
    # Assert: response.compensacion_historica.periodo_dias=30
```

---

## 5. Criterios del Gauntlet

**Criterios de aceptación antes de merge a `main`:**

- [ ] **Tests:** `pytest -n auto` verde; +7 tests nuevos en ruta de integración y unitarias.
- [ ] **Arquitectura:** No duplicación de lógica.
  - `ConsultarAnaliticaPlantaUseCase` y `ConsultarNodoUnifilarUseCase._calcular_compensacion_historica()` reutilizan `DimensionadorCompensacionService`.
- [ ] **Type Checking:** `pyright --project .` cero errores.
- [ ] **Comportamiento:**
  - `/banco-capacitores/planta?planta_id=X&periodo_dias=30` retorna P, Q, FP **reales**, no simulados.
  - `/nodo/unifilar/{nodo_id}?periodo_dias=30` expone parámetro; valores difieren de `?periodo_dias=7`.
  - Si `Q_max <= 0.0` → `sobrecompensacion_sostenida=true`, `banco_recomendado=None`.
- [ ] **Backward Compatibility:** Default a 30 días (cambio de 7); sin breaking changes en DTOs.
- [ ] **Documentación:** Comentar por qué `periodo_dias=30` es estándar (ISO 50001).

---

**Estado:** Listo para implementación.
