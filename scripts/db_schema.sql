-- Bid Master System — PostgreSQL Schema v1
-- 2026-05-18: Phase A migration foundation (mirror of Google Sheets)
--
-- ตารางทั้งหมดออกแบบให้รับข้อมูลจาก existing Sheets schema 1:1
-- + เพิ่ม index ที่จำเป็นสำหรับ analytics queries (#3 priority)

-- ============================================================
-- all_jobs — single source of truth สำหรับงานทุกชิ้น
-- ============================================================
CREATE TABLE IF NOT EXISTS all_jobs (
    job_id              VARCHAR(20) PRIMARY KEY,
    title               TEXT NOT NULL DEFAULT '',
    department          TEXT NOT NULL DEFAULT '',
    province            VARCHAR(50) NOT NULL DEFAULT '',
    district            VARCHAR(50) NOT NULL DEFAULT '',
    subdistrict         VARCHAR(50) NOT NULL DEFAULT '',
    procurement_type    VARCHAR(50) NOT NULL DEFAULT '',
    budget              VARCHAR(50) NOT NULL DEFAULT '',
    publish_date        VARCHAR(20) NOT NULL DEFAULT '',
    deadline            VARCHAR(20) NOT NULL DEFAULT '',
    project_status      VARCHAR(50) NOT NULL DEFAULT '',
    search_keyword      VARCHAR(200) NOT NULL DEFAULT '',
    tor_url             TEXT NOT NULL DEFAULT '',
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP,
    step_id             VARCHAR(10) NOT NULL DEFAULT '',
    project_status_raw  VARCHAR(10) NOT NULL DEFAULT '',
    announce_type       VARCHAR(10) NOT NULL DEFAULT '',
    -- 2026-05-19: Phase 1+2 multi-dim classifier tags
    project_type            VARCHAR(20) NOT NULL DEFAULT '',
    construction_subtype    VARCHAR(20) NOT NULL DEFAULT '',
    budget_tier             VARCHAR(20) NOT NULL DEFAULT '',
    urgency_tier            VARCHAR(20) NOT NULL DEFAULT '',
    method_id               VARCHAR(5)  NOT NULL DEFAULT '',
    sme_suitable            VARCHAR(5)  NOT NULL DEFAULT '',
    geographic_precision    VARCHAR(20) NOT NULL DEFAULT '',
    unspsc_family           VARCHAR(10) NOT NULL DEFAULT '',
    -- Metadata
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_all_jobs_province ON all_jobs(province);
CREATE INDEX IF NOT EXISTS idx_all_jobs_step_id ON all_jobs(step_id);
CREATE INDEX IF NOT EXISTS idx_all_jobs_announce ON all_jobs(announce_type);
CREATE INDEX IF NOT EXISTS idx_all_jobs_publish ON all_jobs(publish_date);
CREATE INDEX IF NOT EXISTS idx_all_jobs_dept ON all_jobs(department);
-- Phase 1+2 classifier indexes (สำหรับ filter ใน SaaS)
CREATE INDEX IF NOT EXISTS idx_all_jobs_project_type ON all_jobs(project_type);
CREATE INDEX IF NOT EXISTS idx_all_jobs_budget_tier ON all_jobs(budget_tier);
CREATE INDEX IF NOT EXISTS idx_all_jobs_urgency_tier ON all_jobs(urgency_tier);
CREATE INDEX IF NOT EXISTS idx_all_jobs_construction_sub ON all_jobs(construction_subtype);

-- ============================================================
-- winners — ผู้ชนะการเสนอราคา (refresh from process5 + CGD)
-- ============================================================
CREATE TABLE IF NOT EXISTS winners (
    job_id          VARCHAR(20) PRIMARY KEY REFERENCES all_jobs(job_id) ON DELETE CASCADE,
    winner_name     TEXT NOT NULL DEFAULT '',
    winner_tin      VARCHAR(20) NOT NULL DEFAULT '',
    winner_price    VARCHAR(50) NOT NULL DEFAULT '',
    discount_pct    VARCHAR(10) NOT NULL DEFAULT '',
    award_date      VARCHAR(20) NOT NULL DEFAULT '',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_winners_tin ON winners(winner_tin);

-- ============================================================
-- bid_history — เก็บ bidders ทุกคนต่อ 1 job (Phase B feature)
-- ============================================================
CREATE TABLE IF NOT EXISTS bid_history (
    id              SERIAL PRIMARY KEY,
    job_id          VARCHAR(20) NOT NULL REFERENCES all_jobs(job_id) ON DELETE CASCADE,
    bidder_name     TEXT NOT NULL DEFAULT '',
    bidder_tin      VARCHAR(20) NOT NULL DEFAULT '',
    price_proposal  VARCHAR(50) NOT NULL DEFAULT '',
    price_agree     VARCHAR(50) NOT NULL DEFAULT '',
    result_flag     VARCHAR(20) NOT NULL DEFAULT '',
    is_winner       BOOLEAN NOT NULL DEFAULT FALSE,
    is_sme          BOOLEAN NOT NULL DEFAULT FALSE,
    is_joint_venture BOOLEAN NOT NULL DEFAULT FALSE,
    jv_partners     TEXT NOT NULL DEFAULT '',
    consider_desc   TEXT NOT NULL DEFAULT '',
    fetched_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bid_history_job ON bid_history(job_id);
CREATE INDEX IF NOT EXISTS idx_bid_history_tin ON bid_history(bidder_tin);

-- ============================================================
-- dept_catalog — replace egp_deptid_catalog.json
-- ============================================================
CREATE TABLE IF NOT EXISTS dept_catalog (
    dept_id         VARCHAR(4) PRIMARY KEY,
    dept_name       TEXT NOT NULL DEFAULT '',
    item_count      INTEGER NOT NULL DEFAULT 0,
    project_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    sample_titles   JSONB NOT NULL DEFAULT '[]'::jsonb,
    pub_dates       JSONB NOT NULL DEFAULT '[]'::jsonb,
    source          VARCHAR(50) NOT NULL DEFAULT '',
    enriched_at     TIMESTAMP,
    scanned_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dept_catalog_active ON dept_catalog(item_count) WHERE item_count > 0;

-- ============================================================
-- customers — SaaS subscribers (mirror customers sheet)
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    line_user_id    VARCHAR(50) PRIMARY KEY,
    display_name    TEXT NOT NULL DEFAULT '',
    email           VARCHAR(255) NOT NULL DEFAULT '',
    phone           VARCHAR(30) NOT NULL DEFAULT '',
    provinces       TEXT NOT NULL DEFAULT '', -- comma-separated
    districts       TEXT NOT NULL DEFAULT '',
    keywords        TEXT NOT NULL DEFAULT '',
    status          VARCHAR(20) NOT NULL DEFAULT 'trial',
    registered_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMP,
    last_active_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_customers_expires ON customers(expires_at);

-- ============================================================
-- pipeline_runs — track pipeline executions (for dashboard)
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              SERIAL PRIMARY KEY,
    run_date        DATE NOT NULL,
    phase           VARCHAR(20) NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    duration_sec    INTEGER,
    total_raw       INTEGER NOT NULL DEFAULT 0,
    total_filtered  INTEGER NOT NULL DEFAULT 0,
    total_new       INTEGER NOT NULL DEFAULT 0,
    cloudflare_hits INTEGER NOT NULL DEFAULT 0,
    classifier_counts JSONB,
    notes           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date ON pipeline_runs(run_date);

-- ============================================================
-- Helper view: active_jobs (อิงจาก step_id + deadline)
-- ============================================================
CREATE OR REPLACE VIEW active_jobs AS
SELECT * FROM all_jobs
WHERE announce_type = 'D0' OR step_id LIKE 'M%' OR step_id LIKE 'S%';

-- ============================================================
-- Auto-update updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_all_jobs_updated ON all_jobs;
CREATE TRIGGER trg_all_jobs_updated BEFORE UPDATE ON all_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_winners_updated ON winners;
CREATE TRIGGER trg_winners_updated BEFORE UPDATE ON winners
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_dept_catalog_updated ON dept_catalog;
CREATE TRIGGER trg_dept_catalog_updated BEFORE UPDATE ON dept_catalog
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_customers_updated ON customers;
CREATE TRIGGER trg_customers_updated BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- competitor_profiles -- aggregated bidder stats per TIN
-- (Materialized view, refresh after ETL or nightly)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS competitor_profiles AS
SELECT
    bh.bidder_tin,
    MAX(bh.bidder_name)                                     AS company_name,
    COUNT(DISTINCT bh.job_id)                               AS total_bids,
    COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END) AS total_wins,
    ROUND(
        100.0 * COUNT(DISTINCT CASE WHEN bh.is_winner THEN bh.job_id END)
        / NULLIF(COUNT(DISTINCT bh.job_id), 0), 1
    )                                                       AS win_rate_pct,
    BOOL_OR(bh.is_sme)                                      AS is_sme,
    BOOL_OR(bh.is_joint_venture)                            AS has_jv,
    MIN(aj.publish_date)                                    AS first_seen,
    MAX(aj.publish_date)                                    AS last_seen,
    ARRAY_AGG(DISTINCT aj.province ORDER BY aj.province)    AS provinces,
    ARRAY_AGG(DISTINCT aj.procurement_type
              ORDER BY aj.procurement_type)                 AS proc_types,
    AVG(
        CASE
            WHEN bh.price_proposal ~ '^[0-9]+(\.[0-9]+)?$'
             AND bh.price_agree    ~ '^[0-9]+(\.[0-9]+)?$'
             AND bh.price_agree::NUMERIC > 0
            THEN 100.0 * (bh.price_proposal::NUMERIC - bh.price_agree::NUMERIC)
                 / bh.price_proposal::NUMERIC
        END
    )                                                       AS avg_discount_pct
FROM bid_history bh
JOIN all_jobs aj ON aj.job_id = bh.job_id
WHERE bh.bidder_tin <> ''
GROUP BY bh.bidder_tin
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_profiles_tin
    ON competitor_profiles(bidder_tin);
CREATE INDEX IF NOT EXISTS idx_competitor_profiles_wins
    ON competitor_profiles(total_wins DESC);
