-- Migration 002 — Classifier Phase 1+2: เพิ่ม 8 columns ใน all_jobs
-- 2026-05-19
--
-- รัน: psql $DATABASE_URL -f scripts/db_migration_002_classifier_tags.sql
-- (idempotent — รันซ้ำได้)

ALTER TABLE all_jobs
    ADD COLUMN IF NOT EXISTS project_type         VARCHAR(20) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS construction_subtype VARCHAR(20) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS budget_tier          VARCHAR(20) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS urgency_tier         VARCHAR(20) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS method_id            VARCHAR(5)  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS sme_suitable         VARCHAR(5)  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS geographic_precision VARCHAR(20) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS unspsc_family        VARCHAR(10) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_all_jobs_project_type      ON all_jobs(project_type);
CREATE INDEX IF NOT EXISTS idx_all_jobs_budget_tier       ON all_jobs(budget_tier);
CREATE INDEX IF NOT EXISTS idx_all_jobs_urgency_tier      ON all_jobs(urgency_tier);
CREATE INDEX IF NOT EXISTS idx_all_jobs_construction_sub  ON all_jobs(construction_subtype);
