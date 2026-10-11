-- Diagnóstico Issue #4 (datamaq-automation/datamaq#4): pico de 22 811 kW en Durax
-- y 40 alertas abiertas de SOBRECOMPENSACION_REACTIVA.
-- Procedimiento de origen: specs/diagnostico-muestras-crudas-durax-y-usuario-ro.md
--
-- SOLO LECTURA. No contiene INSERT, UPDATE, DELETE ni DDL.
-- Esquema verificado contra src/infrastructure/sqlalchemy/models.py:
--   telemetry_instantaneous (device_id, recorded_at, total_active_power, ...)
--   device_alerts (device_id, alert_type, severity, is_resolved, triggered_at, ...)
--   devices (id, device_uid, name)
-- UNIDADES: total_active_power, total_reactive_power y total_apparent_power se guardan en
--   W, VAr y VA (no en kW). Por eso los umbrales de este archivo van en W.
-- FECHAS: recorded_at y triggered_at se guardan en UTC (UtcDateTime), por eso se usa UTC_TIMESTAMP().
-- Nombre de base: el default del código es `datamaq_telemetry` (config.py:19). Confirmar con
--   el .env de producción antes de correr; el spec original decía `datamaq`.

-- 0. Confirmar base y columnas (lectura de información_schema)
SELECT DATABASE() AS base_actual;
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND ((table_name = 'telemetry_instantaneous' AND column_name IN ('total_active_power', 'es_dato_confiable', 'recorded_at'))
    OR (table_name = 'device_alerts' AND column_name IN ('alert_type', 'is_resolved', 'triggered_at')));

-- 1. Pico de potencia activa total (> 1 MW = 1 000 000 W)
--    Umbral de 1 MW: el pico reportado es ~22 811 kW (~22 811 000 W).
SELECT t.id, t.device_id, d.device_uid, d.name AS dispositivo,
       t.recorded_at, t.total_active_power, t.total_reactive_power,
       t.total_apparent_power, t.total_power_factor, t.voltage_linea_V,
       t.es_dato_confiable
FROM telemetry_instantaneous AS t
JOIN devices AS d ON d.id = t.device_id
WHERE t.total_active_power > 1000000
ORDER BY t.total_active_power DESC
LIMIT 10;

-- 2. Ráfaga o duplicación alrededor del pico.
--    Reemplazar '2026-MM-DD HH:MM:SS' por recorded_at del pico (Consulta 1) y el device_id correspondiente.
SELECT id, recorded_at, total_active_power,
       active_power_r, active_power_s, active_power_t,
       es_dato_confiable
FROM telemetry_instantaneous
WHERE device_id = 'REEMPLAZAR_DEVICE_ID'
  AND recorded_at BETWEEN DATE_SUB('2026-MM-DD HH:MM:SS', INTERVAL 2 MINUTE)
                      AND DATE_ADD('2026-MM-DD HH:MM:SS', INTERVAL 2 MINUTE)
ORDER BY recorded_at ASC;

-- 3. Auditoría de alertas abiertas de sobrecompensación reactiva
SELECT alert_type, severity,
       COUNT(*) AS total_abiertas,
       MIN(triggered_at) AS primera_alerta,
       MAX(triggered_at) AS ultima_alerta,
       COUNT(DISTINCT device_id) AS dispositivos_afectados
FROM device_alerts
WHERE is_resolved = 0
  AND alert_type = 'SOBRECOMPENSACION_REACTIVA'
GROUP BY alert_type, severity;

-- 4. Medias de las últimas 24 h por dispositivo (sólo lecturas confiables)
SELECT t.device_id, d.name AS dispositivo,
       AVG(t.total_active_power) AS p_media_w,
       AVG(t.total_reactive_power) AS q_media_var,
       AVG(t.total_power_factor) AS fp_medio,
       MIN(t.total_power_factor) AS fp_minimo,
       COUNT(*) AS muestras
FROM telemetry_instantaneous AS t
JOIN devices AS d ON d.id = t.device_id
WHERE t.recorded_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 24 HOUR)
  AND t.es_dato_confiable = 1
GROUP BY t.device_id, d.name;
