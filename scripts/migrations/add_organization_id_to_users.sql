-- Migración: Etapa 1 multi-tenancy — Agregar organization_id a users
-- Fecha: 2026-09-09
-- Descripción: Vincula cada usuario a una organización para habilitar
--              aislamiento de datos por organización en el API.

ALTER TABLE users
    ADD COLUMN organization_id VARCHAR(36) NULL AFTER totp_backup_codes,
    ADD CONSTRAINT fk_users_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE SET NULL;
