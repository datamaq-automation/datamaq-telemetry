-- Datamaq Telemetry Database Schema (MySQL / MariaDB)
CREATE DATABASE IF NOT EXISTS `datamaq_telemetry`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `datamaq_telemetry`;

-- 0. Subscription Plans (Catálogo SaaS Freemium)
CREATE TABLE IF NOT EXISTS `plans` (
    `id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `description` TEXT NOT NULL,
    `monthly_price_ars` DECIMAL(12, 2) NOT NULL,
    `visibility` VARCHAR(20) NOT NULL DEFAULT 'PUBLICO',
    `retention_days` INT NOT NULL,
    `granularity_minutes` INT NOT NULL,
    `max_devices` INT NOT NULL,
    `notification_channels` JSON NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1. Organizations (Clientes / Empresas)
CREATE TABLE IF NOT EXISTS `organizations` (
    `id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    `plan_id` VARCHAR(36) DEFAULT NULL,
    `tax_id` VARCHAR(50) DEFAULT NULL,
    `contact_email` VARCHAR(120) DEFAULT NULL,
    `contact_phone` VARCHAR(50) DEFAULT NULL,
    `pro_expires_at` DATETIME DEFAULT NULL,
    `free_tier_mode` VARCHAR(30) NOT NULL DEFAULT 'PRIVADO_BASICO',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_organizations_plan` FOREIGN KEY (`plan_id`) REFERENCES `plans` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Facilities (Plantas / Sedes / Establecimientos)
CREATE TABLE IF NOT EXISTS `facilities` (
    `id` VARCHAR(36) NOT NULL,
    `organization_id` VARCHAR(36) NOT NULL,
    `name` VARCHAR(150) NOT NULL,
    `address` VARCHAR(255) DEFAULT NULL,
    `latitude` DECIMAL(10, 8) DEFAULT NULL,
    `longitude` DECIMAL(11, 8) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_facilities_org` FOREIGN KEY (`organization_id`) REFERENCES `organizations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Devices (Medidores Powermeter)
CREATE TABLE IF NOT EXISTS `devices` (
    `id` VARCHAR(36) NOT NULL,
    `facility_id` VARCHAR(36) DEFAULT NULL,
    `device_uid` VARCHAR(64) NOT NULL, -- MAC Address o Client ID (ej: D48C49F03564)
    `serial_number` VARCHAR(64) DEFAULT NULL,
    `name` VARCHAR(100) NOT NULL DEFAULT 'Nuevo Dispositivo',
    `model` VARCHAR(50) DEFAULT 'SmartPlus',
    `hw_version` VARCHAR(50) DEFAULT NULL,
    `fw_version` VARCHAR(50) DEFAULT NULL,
    `tag_location` VARCHAR(100) DEFAULT NULL, -- ej: Tablero Principal / Bomba 1
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `status` VARCHAR(20) NOT NULL DEFAULT 'OFFLINE', -- ONLINE, OFFLINE, WARNING
    `last_seen_at` DATETIME DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_devices_uid` (`device_uid`),
    KEY `idx_devices_facility` (`facility_id`),
    CONSTRAINT `fk_devices_facility` FOREIGN KEY (`facility_id`) REFERENCES `facilities` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Instantaneous Telemetry (V, I, P, Q, S, FP)
CREATE TABLE IF NOT EXISTS `telemetry_instantaneous` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `device_id` VARCHAR(36) NOT NULL,
    `recorded_at` DATETIME(3) NOT NULL,
    -- Fase R
    `voltage_r` DECIMAL(6, 2) DEFAULT NULL,
    `current_r` DECIMAL(6, 2) DEFAULT NULL,
    `active_power_r` DECIMAL(10, 2) DEFAULT NULL,
    `reactive_power_r` DECIMAL(10, 2) DEFAULT NULL,
    `apparent_power_r` DECIMAL(10, 2) DEFAULT NULL,
    `power_factor_r` DECIMAL(4, 2) DEFAULT NULL,
    -- Fase S
    `voltage_s` DECIMAL(6, 2) DEFAULT NULL,
    `current_s` DECIMAL(6, 2) DEFAULT NULL,
    `active_power_s` DECIMAL(10, 2) DEFAULT NULL,
    `reactive_power_s` DECIMAL(10, 2) DEFAULT NULL,
    `apparent_power_s` DECIMAL(10, 2) DEFAULT NULL,
    `power_factor_s` DECIMAL(4, 2) DEFAULT NULL,
    -- Fase T
    `voltage_t` DECIMAL(6, 2) DEFAULT NULL,
    `current_t` DECIMAL(6, 2) DEFAULT NULL,
    `active_power_t` DECIMAL(10, 2) DEFAULT NULL,
    `reactive_power_t` DECIMAL(10, 2) DEFAULT NULL,
    `apparent_power_t` DECIMAL(10, 2) DEFAULT NULL,
    `power_factor_t` DECIMAL(4, 2) DEFAULT NULL,
    -- Totales
    `total_active_power` DECIMAL(12, 2) DEFAULT NULL,
    `total_reactive_power` DECIMAL(12, 2) DEFAULT NULL,
    `total_apparent_power` DECIMAL(12, 2) DEFAULT NULL,
    `total_power_factor` DECIMAL(4, 2) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_telemetry_inst_dev_time` (`device_id`, `recorded_at`),
    KEY `idx_telemetry_inst_time` (`recorded_at`),
    CONSTRAINT `fk_telemetry_inst_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Accumulated Energy Telemetry (kWh, kVARh)
CREATE TABLE IF NOT EXISTS `telemetry_energy` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `device_id` VARCHAR(36) NOT NULL,
    `recorded_at` DATETIME(3) NOT NULL,
    `net_active_energy_kwh` DECIMAL(14, 3) DEFAULT NULL,
    `net_reactive_energy_kvarh` DECIMAL(14, 3) DEFAULT NULL,
    `imported_active_energy_kwh` DECIMAL(14, 3) DEFAULT NULL,
    `exported_active_energy_kwh` DECIMAL(14, 3) DEFAULT NULL,
    `imported_reactive_energy_kvarh` DECIMAL(14, 3) DEFAULT NULL,
    `exported_reactive_energy_kvarh` DECIMAL(14, 3) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_telemetry_energy_dev_time` (`device_id`, `recorded_at`),
    KEY `idx_telemetry_energy_time` (`recorded_at`),
    CONSTRAINT `fk_telemetry_energy_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Device Status Logs (Calidad Wi-Fi, Uptime, IP)
CREATE TABLE IF NOT EXISTS `device_status_logs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `device_id` VARCHAR(36) NOT NULL,
    `recorded_at` DATETIME(3) NOT NULL,
    `wifi_rssi_dbm` INT DEFAULT NULL,
    `wifi_quality` INT DEFAULT NULL,
    `ip_address` VARCHAR(45) DEFAULT NULL,
    `uptime_seconds` BIGINT DEFAULT NULL,
    `raw_payload` JSON DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_device_status_dev_time` (`device_id`, `recorded_at`),
    KEY `idx_device_status_time` (`recorded_at`),
    CONSTRAINT `fk_device_status_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Device Alerts
CREATE TABLE IF NOT EXISTS `device_alerts` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `device_id` VARCHAR(36) NOT NULL,
    `alert_type` VARCHAR(50) NOT NULL,
    `severity` ENUM('INFO', 'WARNING', 'CRITICAL') NOT NULL DEFAULT 'WARNING',
    `message` TEXT NOT NULL,
    `is_resolved` BOOLEAN NOT NULL DEFAULT FALSE,
    `triggered_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `resolved_at` DATETIME(3) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_alerts_dev_resolved` (`device_id`, `is_resolved`),
    KEY `idx_alerts_resolved_purge` (`is_resolved`, `resolved_at`),
    CONSTRAINT `fk_alerts_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
