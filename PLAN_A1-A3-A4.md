# Plan Ejecución: A1, A3, A4 (2026-10-05)

## Orden de Ejecución

**Secuencia recomendada:**

1. **A4 primero** (1 sprint): Crear `RotacionFasorial` value object
   - Prerequisito para A3 (A3 usará RotacionFasorial)
   - Prerequisito para A1 (A1 validará con R:0,S:15, que es instancia de RotacionFasorial)

2. **A3 después** (1 sprint): Cambiar métrica de scoring en diagnostico_ti.py
   - Depende de A4 (usará RotacionFasorial)

3. **A1 en paralelo a A3** (1 sprint): Validar energía Trafo 2
   - No depende de A3/A4
   - Puede ejecutarse simultáneamente

---

## A4: Crear RotacionFasorial Value Object

**Archivo destino:** `src/domain/telemetria/value_objects.py`

**Qué crear:**
```python
@dataclass(frozen=True)
class RotacionFasorial:
    """Rotación fasorial: reorden + inversión + ángulos."""

    r_deg: float = 0.0
    s_deg: float = 0.0
    t_deg: float = 0.0
    invertida: bool = False

    def aplicar(self, p: float, q: float, fase: str) -> tuple[float, float]:
        """Aplica rotación a potencias (P, Q) según fase."""
        # Retorna (p_rotado, q_rotado)
```

**Dónde eliminar duplicación:**
- `src/domain/telemetria/servicios/diagnostico_ti.py` línea 52–87: reemplazar `aplicar_transformacion_ti()` por `RotacionFasorial.aplicar()`
- `src/domain/telemetria/servicios/analizador_fasorial.py` línea 50–75: usar `RotacionFasorial` para rotaciones de ángulos

**Criterio éxito:**
- RotacionFasorial creado con método `aplicar()`
- Ambos servicios lo usan
- Tests verifican que `aplicar()` produce mismo resultado en ambos contextos
- Duplicación eliminada

---

## A3: Cambiar Métrica de Scoring

**Archivo destino:** `src/domain/telemetria/servicios/diagnostico_ti.py` línea 135

**Cambio:**
```python
# Hoy:
score = max(0.0, 100.0 - (err_s_prom + err_fp_prom) / 2.0) / 100.0

# Opción recomendada (pesos):
score = max(0.0, 100.0 - (0.7 * err_s_prom + 0.3 * err_fp_prom)) / 100.0
```

(70% peso a coherencia S porque TI afecta más a S que a FP)

**Criterio éxito:**
- Método de scoring NO promedia S + FP
- Mejor candidato (H-e para Trafo 2, R:0,S:15) rankea #1
- Tests verifican mayor separación entre scores

---

## A1: Validar Energía Trafo 2 + Rotación R:0,S:15

**Qué hacer:**
1. Obtener energía histórica medidor 369 (c91713f1...) desde 17/9 hasta 5/10
   - Datos disponibles: 4,122.35 kWh netos
2. Validar coherencia con rotación propuesta R:0,S:15
3. (Opcional) Comparar contra factura cuando tengamos D2–D3

**Archivos a modificar/crear:**
- Script de validación: `scripts/validar_energia_trafo2_rotacion.py` (nuevo)
- O tests en `tests/unit/test_validacion_energia.py` (nuevo)

**Criterio éxito:**
- Energía histórica extraída con precisión
- Coherencia fasorial con R:0,S:15 validada
- Reporte de resultados generado

---

## Commits Esperados

```
feat(a4): crear value object RotacionFasorial para consolidar lógica fasorial
refactor(diagnostico): usar RotacionFasorial en diagnostico_ti.py
refactor(fasorial): usar RotacionFasorial en analizador_fasorial.py
feat(a3): cambiar métrica de scoring a pesos (70% S, 30% FP)
test(diagnostico): verificar mejor discriminación entre candidatos
feat(a1): validar energía histórica trafo 2 + rotación R:0,S:15
```

---

## Próximos Pasos

1. **Sesión hija comienza con A4** (crear RotacionFasorial)
2. A3 y A1 en paralelo cuando A4 esté listo
3. Reportar avance después de cada sprint (A4 → A3 → A1)

