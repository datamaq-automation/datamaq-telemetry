# Plan Detallado: Detección Automática de Anomalías TI (3 Capas)

**Autor:** Claude Haiku 4.5  
**Fecha:** 2026-09-27  
**Estado:** Plan de Arquitectura (Implementación: Sesión siguiente)

---

## 1. Estructura de Datos

### Tabla: `telemetria_anomalias` (Nueva Migración)

```sql
CREATE TABLE telemetria_anomalias (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(36) NOT NULL,
    recorded_at DATETIME NOT NULL,
    error_s FLOAT NOT NULL COMMENT 'Error % entre S medida y S teórica',
    flag_tipo ENUM('coherencia_baja', 'degradacion', 'otros') NOT NULL,
    contador_consecutivos INT DEFAULT 1,
    estado ENUM('active', 'resolved') DEFAULT 'active',
    creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
    actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES dispositivos(device_id),
    INDEX idx_device_recorded (device_id, recorded_at),
    INDEX idx_estado (estado)
);
```

### Tabla: `dispositivo_diagnosticos` (Nueva Migración)

```sql
CREATE TABLE dispositivo_diagnosticos (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(36) NOT NULL,
    ejecutado_en DATETIME NOT NULL,
    config_actual VARCHAR(50) COMMENT 'R,S,T o S,R,T (formato)',
    config_actual_invertido BOOLEAN,
    top_candidato VARCHAR(50),
    top_candidato_invertido BOOLEAN,
    top_score FLOAT,
    registros_analizados INT,
    mismatch BOOLEAN COMMENT 'true si top != actual',
    alerta_enviada BOOLEAN DEFAULT false,
    creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES dispositivos(device_id),
    INDEX idx_device_ejecutado (device_id, ejecutado_en)
);
```

---

## 2. Capa 1: Validación en Ingesta (Inmediata)

### Ubicación
- **Dónde:** `src/application/use_cases/ingestar_telemetria.py` → método `ejecutar()`
- **Cuándo:** Después de guardar cada telemetría instantánea

### Lógica

```python
def _validar_coherencia_fasorial(self, registro: dict) -> bool:
    """
    Calcula error_s para cada fase y retorna si flag debe activarse.

    Args:
        registro: dict con p_r, q_r, s_r, p_s, q_s, s_s, etc.

    Returns:
        bool: True si error_s > 15% en cualquier fase
    """
    errores = []
    for fase in ["r", "s", "t"]:
        p = registro.get(f"active_power_{fase}")
        q = registro.get(f"reactive_power_{fase}")
        s_medida = registro.get(f"apparent_power_{fase}")

        if p is not None and q is not None and s_medida is not None:
            s_teorica = math.sqrt(p**2 + q**2)
            error_pct = 100 * abs(s_medida - s_teorica) / s_teorica if s_teorica > 0 else 0
            errores.append(error_pct)

    max_error = max(errores) if errores else 0
    return max_error > 15.0  # Umbral 15%
```

### Persistencia

```python
# En ingestar_telemetria.py:

# Persistir flag en telemetria_anomalias
if _validar_coherencia_fasorial(registro):
    anomalia = TelemetriaAnomalia(
        device_id=dispositivo_id,
        recorded_at=timestamp,
        error_s=max_error,
        flag_tipo="coherencia_baja",
        contador_consecutivos=1,
    )
    db.add(anomalia)

    # Contar consecutivos para escalada
    ultimas_10 = (
        db.query(TelemetriaAnomalia)
        .filter(TelemetriaAnomalia.device_id == dispositivo_id)
        .filter(TelemetriaAnomalia.flag_tipo == "coherencia_baja")
        .order_by(desc(TelemetriaAnomalia.recorded_at))
        .limit(10)
        .all()
    )

    if len(ultimas_10) >= 10:
        # Marcar dispositivo como WARN
        dispositivo.estado_coherencia = "WARN"
        logger.warning(f"WARN: {dispositivo_id} tiene 10+ flags consecutivos")

    if len(ultimas_10) >= 100:  # 1+ día si cada 15min
        # Marcar como ERROR
        dispositivo.estado_coherencia = "ERROR"
        logger.error(f"ERROR: {dispositivo_id} degradación crítica (100+ flags)")
```

### Tests a Crear

**`tests/unit/test_validacion_coherencia_fasorial.py`**
- Test: ingestar con coherencia buena (< 5%) → sin flag
- Test: ingestar con coherencia mala (> 30%) → flag
- Test: 10+ flags consecutivos → dispositivo WARN
- Test: 100+ flags → dispositivo ERROR

---

## 3. Capa 2: Test en Gauntlet (Diaria)

### Ubicación
- **Archivo:** `tests/integration/test_coherencia_dispositivos.py`
- **Cuándo:** En gauntlet pre-push, integrado en Stage 4 (Tests Unitarios)

### Lógica

```python
def test_coherencia_dispositivos_vs_baseline():
    """
    Para cada dispositivo en producción:
    1. Calcular coherencia promedio últimas 24h
    2. Comparar vs baseline 7 días
    3. FAIL si degradación > 20%
    """
    session = get_session_factory()()
    repo_disp = MySQLDispositivosRepository(session)
    repo_tele = MySQLTelemetriaRepository(session)

    dispositivos = repo_disp.listar()  # Todos

    resultados = []
    for dispositivo in dispositivos:
        # Últimas 24h
        ahora = datetime.now(timezone.utc)
        hace_24h = ahora - timedelta(hours=24)

        mediciones_24h = repo_tele.obtener_por_rango(dispositivo_id=dispositivo.device_id, inicio=hace_24h, fin=ahora)

        coherencia_24h = _calcular_coherencia_promedio(mediciones_24h)

        # Baseline últimos 7 días
        hace_7d = ahora - timedelta(days=7)
        mediciones_7d = repo_tele.obtener_por_rango(dispositivo_id=dispositivo.device_id, inicio=hace_7d, fin=ahora)
        coherencia_baseline = _calcular_coherencia_promedio(mediciones_7d)

        # Comparar
        degradacion_pct = (coherencia_baseline - coherencia_24h) / coherencia_baseline * 100

        resultados.append(
            {
                "device_id": dispositivo.device_id,
                "coherencia_24h": coherencia_24h,
                "baseline_7d": coherencia_baseline,
                "degradacion_pct": degradacion_pct,
                "ok": degradacion_pct <= 20.0,  # Umbral 20%
            }
        )

    # FAIL si alguno excede umbral
    fallos = [r for r in resultados if not r["ok"]]
    assert not fallos, f"Degradación detectada:\n{fallos}"

    # Guardar reporte CSV en artifact para auditoría
    _guardar_reporte_coherencia(resultados)
```

### Función Helper

```python
def _calcular_coherencia_promedio(mediciones: list[dict]) -> float:
    """
    Calcula score de coherencia promedio: 1 - (error_s_promedio / 100)

    Score 1.0 = perfecto
    Score 0.8 = 20% error promedio (bueno)
    Score 0.5 = 50% error promedio (malo)
    """
    if not mediciones:
        return 0.0

    errores = []
    for med in mediciones:
        for fase in ["r", "s", "t"]:
            p = med.get(f"p_{fase}")
            q = med.get(f"q_{fase}")
            s = med.get(f"s_{fase}")

            if p and q and s:
                s_teorica = math.sqrt(p**2 + q**2)
                error = 100 * abs(s - s_teorica) / s_teorica if s_teorica > 0 else 0
                errores.append(error)

    error_promedio = sum(errores) / len(errores) if errores else 0
    return max(0.0, 1.0 - error_promedio / 100.0)  # Clamp a [0, 1]
```

### Tests a Crear

**`tests/integration/test_coherencia_dispositivos.py`**
- Test: dispositivos correctos pasan (degradación <= 20%)
- Test: dispositivo simulado degradado falla (degradación > 20%)
- Test: reporte CSV generado correctamente

---

## 4. Capa 3: Job Background (Semanal)

### Ubicación
- **Archivo:** `scripts/job_diagnostico_semanal.py` (nuevo)
- **Scheduler:** `src/infrastructure/jobs/scheduler.py` (nuevo)
- **Cuándo:** Lunes 3 AM UTC

### Lógica

```python
# scripts/job_diagnostico_semanal.py


def ejecutar_diagnostico_semanal():
    """
    Ejecuta cada lunes a las 3 AM:
    1. Para cada dispositivo con TI
    2. Ejecutar diagnóstico 7 días histórico
    3. Comparar top candidato vs config guardada
    4. Si mismatch + score > 0.95 → alertar ops
    """
    session_factory = get_session_factory()

    with session_factory() as session:
        repo_disp = MySQLDispositivosRepository(session)
        dispositivos = repo_disp.listar()

        alertas = []

        for dispositivo in dispositivos:
            if not dispositivo.fases_con_ti:
                continue  # No tiene TI

            # Ejecutar diagnóstico
            adapter = TelemetriaDiagnosticoAdapter(session)
            service = EjecutarDiagnosticoTIApplicationService(adapter)

            fases = tuple(f.strip().upper() for f in dispositivo.fases_con_ti.split(","))
            result = service.ejecutar(
                dispositivo_id=dispositivo.device_id,
                fases_con_ti=fases,
                periodo_horas=24 * 7,  # 7 días
            )

            if result.error or not result.candidatos:
                continue

            top = result.candidatos[0]

            # Guardar en BD
            diagnostico = DispositivoDiagnostico(
                device_id=dispositivo.device_id,
                ejecutado_en=datetime.now(timezone.utc),
                config_actual=",".join(fases),
                config_actual_invertido=dispositivo.invertido,
                top_candidato=",".join(top.orden_fases),
                top_candidato_invertido=top.invertido,
                top_score=top.score,
                registros_analizados=result.registros_analizados,
                mismatch=(top.orden_fases != fases or top.invertido != dispositivo.invertido),
                alerta_enviada=False,
            )
            session.add(diagnostico)

            # Si mismatch + score alto → alerta
            if diagnostico.mismatch and top.score > 0.95:
                alertas.append(
                    {
                        "device_id": dispositivo.device_id,
                        "ubicacion": dispositivo.ubicacion_tag,
                        "config_actual": f"{','.join(fases)}, inv={dispositivo.invertido}",
                        "top_candidato": f"{','.join(top.orden_fases)}, inv={top.invertido}",
                        "score": top.score,
                    }
                )
                diagnostico.alerta_enviada = True

        session.commit()

        # Enviar alertas a Slack (si webhook disponible)
        if alertas:
            _enviar_alerta_slack(alertas)

        logger.info(f"Job semanal completado. {len(alertas)} alertas enviadas.")


def _enviar_alerta_slack(alertas: list):
    """Notificar ops via Slack si hay mismatch crítico."""
    # TODO: Implementar cuando Slack webhook esté disponible
    # Por ahora: solo log
    for alerta in alertas:
        logger.warning(f"ALERTA TI: {alerta['device_id']} mismatch detectado. Score: {alerta['score']:.4f}")
```

### Scheduler

```python
# src/infrastructure/jobs/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def iniciar_scheduler():
    """Inicia scheduler en background."""
    scheduler = BackgroundScheduler()

    # Cada lunes a las 3 AM UTC
    scheduler.add_job(
        func=ejecutar_diagnostico_semanal,
        trigger=CronTrigger(day_of_week=0, hour=3, minute=0),  # 0 = Monday
        id="diagnostico_ti_semanal",
        name="Diagnóstico TI Semanal",
    )

    scheduler.start()
    logger.info("Scheduler iniciado. Job diagnóstico TI: Lunes 3 AM UTC")

    return scheduler
```

### Tests a Crear

**`tests/integration/test_job_diagnostico_semanal.py`**
- Test: ejecutar job, verificar que tablas se llenen
- Test: mismatch detectado y alerta generada
- Test: dispositivo sin TI ignorado

---

## 5. Dependencias de Infraestructura

### Paquetes Nuevos
```bash
pip install apscheduler==3.10.4
```

### Configuración en `main.py`
```python
# src/main.py

from src.infrastructure.jobs.scheduler import iniciar_scheduler


def create_app():
    app = FastAPI(...)

    # Iniciar scheduler en background
    @app.on_event("startup")
    def startup():
        iniciar_scheduler()

    return app
```

### Variables de Entorno (si aplica)
```bash
# .env
JOB_DIAGNOSTICO_TI_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # Opcional, por ahora vacío
```

---

## 6. Orden de Implementación (Sesión Siguiente)

### Fase 1: Estructura de Datos
1. Migración Alembic: crear tablas `telemetria_anomalias` + `dispositivo_diagnosticos`
2. Modelos ORM: `TelemetriaAnomalia`, `DispositivoDiagnostico`
3. Repositorios: métodos en `MySQLTelemetriaRepository`

### Fase 2: Capa 1 (Ingesta)
4. Service: `_validar_coherencia_fasorial()` en `ingestar_telemetria.py`
5. Lógica de flag y escalada
6. Tests: `test_validacion_coherencia_fasorial.py`

### Fase 3: Capa 2 (Gauntlet)
7. Test: `test_coherencia_dispositivos.py`
8. Función helper: `_calcular_coherencia_promedio()`
9. Integrar en Stage 4 del gauntlet

### Fase 4: Capa 3 (Job)
10. Job script: `scripts/job_diagnostico_semanal.py`
11. Scheduler: `src/infrastructure/jobs/scheduler.py`
12. Inicialización en `main.py`
13. Tests: `test_job_diagnostico_semanal.py`

### Fase 5: Integración
14. Gauntlet completo: todas las 3 capas funcionando
15. Validar que no hay errores de tipos (Pyright 0)
16. Push a main

---

## 7. Criterios de Aceptación

✅ **Funcionales:**
- Capa 1 flagea anomalías en ingesta
- Capa 2 FAIL test si degradación > 20%
- Capa 3 detecta mismatch config en 7 días histórico
- Tablas BD con datos correctos
- Job ejecuta sin errores

✅ **No-funcionales:**
- Pyright: 0 errores
- Tests: 100% cobertura de lógica nueva
- Gauntlet: sin regresiones
- Performance: Capa 1 overhead < 5ms/registro, Capa 2 test < 5 min

✅ **Pruebas Manual (antes de push):**
- Retroactiva: Ejecutar Capa 1 sobre histórico San Martín → detectar en < 1 hora
- Gauntlet: Pasar sin degradación falsa en dispositivos correctos
- Job: Ejecutar manualmente, verificar reporte CSV

---

## 8. Dudas Pendientes para Mañana

1. ¿La migración Alembic debe crear las tablas o si le dejo creadas ya?
2. ¿APScheduler se inicia en main() o en conftest() para tests?
3. ¿El Slack webhook está disponible ya, o dejamos por ahora solo log?
4. ¿Cuáles son los valores de coherencia para dispositivos que sí están correctamente configurados? (para calibrar umbrales)

---

## 9. Archivos a Crear/Modificar Resumen

**Nuevos:**
- `migrations/alembic/versions/XXXX_crear_anomalias_diagnosticos.py`
- `src/domain/telemetria/anomalias.py` (Value Objects)
- `src/infrastructure/sqlalchemy/models/telemetria_anomalia.py`
- `src/infrastructure/sqlalchemy/models/dispositivo_diagnostico.py`
- `src/infrastructure/jobs/scheduler.py`
- `scripts/job_diagnostico_semanal.py`
- `tests/integration/test_coherencia_dispositivos.py`
- `tests/integration/test_job_diagnostico_semanal.py`
- `tests/unit/test_validacion_coherencia_fasorial.py`

**Modificados:**
- `src/application/use_cases/ingestar_telemetria.py` (agregar validación)
- `src/infrastructure/sqlalchemy/repositories/telemetria_repository.py` (nuevos métodos)
- `src/main.py` (iniciar scheduler)
- `pyproject.toml` (agregar apscheduler)

---

## 10. Notas Importantes

- ⚠️ **APScheduler en tests:** Usar `BlockingScheduler` para mocks, `BackgroundScheduler` en prod
- ⚠️ **Timezone:** Siempre UTC en BD. Job se ejecuta a 3 AM UTC (ajustar si necesario)
- ⚠️ **Reutilización:** Tanto Capa 1 como Capa 2 usan misma lógica de cálculo error_s → extraer a `DiagnosticoTIService` (ya existe)
- 📌 **Retroactivo:** Una vez implementado, ejecutar manualmente sobre histórico de San Martín para validar
