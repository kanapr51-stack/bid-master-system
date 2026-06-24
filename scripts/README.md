# scripts — สคริปต์อัตโนมัติ

โฟลเดอร์นี้เก็บโค้ด Python ทั้งหมดของ BMS (266 ไฟล์) แบ่งตามหน้าที่ด้านล่าง
ไม่ list รายไฟล์ทั้งหมด — ใช้ `ls scripts/<prefix>*` หรือ grep หาไฟล์เฉพาะที่ต้องการ

> อัปเดตล่าสุด: 2026-06-21 (ก่อนหน้านี้ README ตกรุ่นมาก — เคย list ไว้แค่ 2 ไฟล์)

## 🎯 Pipeline หลัก (production, รันจริงทุกวัน)

| ไฟล์ | หน้าที่ |
|---|---|
| `Sebastian_Pipeline.py` | orchestrator หลัก — `--step all` รันทุก step ตามลำดับ scrape→classify→refresh→download→analyze→cost→rank→notify |
| `Sebastian_RSS_Scraper.py` / `Sebastian_RSS_Probe.py` / `Sebastian_RSS_Notifier.py` | RSS ingestion (D0) |
| `Sebastian_Province_Discovery.py` / `discover_jobs_playwright.py` / `discovery_catchup.py` | province search API discovery (แทน RSS ตอน RSS ล่ม) |
| `Sebastian_Classifier.py` / `work_type_classifier.py` / `classifier_tags.py` | จัดหมวดงานตาม keyword/vocab |
| `job_matcher.py` / `matching_shadow.py` | matching engine + shadow-test ก่อน deploy logic ใหม่ |
| `Sebastian_Cost_Filler.py` / `Sebastian_Ranker.py` | ประเมินต้นทุน + จัดอันดับโอกาส |
| `Sebastian_Winner_Poller.py` / `winner_sweep.py` / `build_winner_cache.py` / `heal_winner_cache.py` | ติดตามผู้ชนะ (W0) + ซ่อม cache |
| `Sebastian_LINE_Notify.py` / `Sebastian_LINE_Push.py` / `Sebastian_LINE_Sender.py` / `Sebastian_Discord_Notify.py` / `Sebastian_Discord_Bot.py` | ส่งแจ้งเตือนลูกค้า/ทีม |
| `Sebastian_Daily_Digest.py` / `Sebastian_Daily_User_Summary.py` / `timeline_reminder.py` / `job_followups.py` | สรุป/ติดตามรายวัน |
| `Sebastian_Enrichment_Worker.py` / `Sebastian_Doc_Downloader.py` / `egp_pdf_parser.py` / `prelim_summary.py` | ดึง/parse เอกสารประกอบ |
| `Sebastian_ETL_Sync.py` / `etl_sheet_to_db.py` | sync Sheets (legacy) ↔ product DB |
| `Sebastian_Telemetry.py` / `Sebastian_WAF_Morning_Pulse.py` / `health_deadman.py` / `queue_health.py` / `sebastian_health_check.py` | monitoring/observability |
| `portal_views.py` / `repredict_followed.py` / `star_metrics.py` | data layer สำหรับ `/portal` web app |
| `deadline_service.py` / `deadline_provider_doczip.py` / `patch_deadlines.py` | deadline extraction (จาก PDF) |
| `token_service.py` / `follow_token.py` | eGP token generation/refresh |

## 🌐 CGD (Comptroller-General's Dept open data)

`cgd_api_client.py`, `cgd_discovery.py`, `cgd_freshness.py`, `cgd_intel.py`, `cgd_resource_catalog.py`, `cgd_sync_to_vps.py`, `cgd_winner_refresh.py`

## 🗺️ Geo / Province extraction

`province_extractor.py`, `geo_reverse.py`, `build_geo_lookup.py`, `gen_thai_geo.py`, `observe_location_resolution.py`

## 🏗️ Infra / core clients (import กันเป็น base)

`bms_api.py`, `bms_paths.py`, `db_client.py`, `customers_db.py`, `sheets_client.py`, `Sebastian_Customer_DB.py`, `Sebastian_JSON_Merger.py`, `Sebastian_AI_Analyzer.py`, `Sebastian_TOR_Analyzer.py`, `Sebastian_PR45_Parser.py`, `Sebastian_Preprocessor.py`, `Sebastian_Shadow_Audit.py`, `Sebastian_Revalidate_Dashboard.py`, `Sebastian_Dashboard_Refresh.py`, `Sebastian_Deploy_Dashboard.py`, `Sebastian_Heatmap.py`, `Sebastian_Upload_Snapshot.py`, `Sebastian_Sheet2_Writer.py`, `Sebastian_XHR_Discovery.py`, `vps_canary.py`, `text_normalize.py`, `bid_field.py`, `bid_history_queries.py`, `fetch_bid_history.py`, `dashboard_extractor.py`, `build_parents_dashboard.py`, `build_org_cache.py`, `build_target_deptids.py`, `filter_target_deptids.py`, `pipeline_funnel.py`, `competitor_trend.py`, `enrich_dept_names.py`, `scraper_metrics.py`, `validate_work_type.py`, `seed_self_notify.py`, `capture_line_userid.py`, `ask_discord.py`

## 🧪 Tests (`test_*.py`, ~70 ไฟล์, pytest)

ครอบคลุม: portal (jobs/notes/stars/routes/views/page), winner (poller/sweep/card/format), matching (job_matcher/province/geo/recency), pricing (price_prediction/winrate/z_blend/round2/upper_bound), deadline, CGD (intel/freshness/sync/winner_refresh), discovery (http/stage_advance/announce). รัน `pytest scripts/ -k <keyword>` เพื่อหา test ที่เกี่ยวกับ feature ที่กำลังแก้

## 🔧 One-off migration / backfill (รันครั้งเดียว ไม่ใช่ pipeline)

`backfill_bidders.py`, `backfill_classifier_tags.py`, `backfill_location.py`, `backfill_province.py`, `backfill_raw_jobs_columns.py`, `migrate_competitor_profiles_v2.py`, `migrate_feedback_schema.py`, `migrate_qualification_schema.py`, `migrate_to_all_jobs.py`, `migrate_work_type_column.py`, `smart_migrate.py`, `reclassify_backlog_by_announcedate.py`, `resend_d0_jobs.py`, `_resend_today_onboarding.py`, `_backfill_home_fetch.py`, `repredict_followed.py`, `cleanup_test_data.py`, `delete_tor_analysis_sheet.py`, `create_new_sheets.py`, `create_calc_sheet.py`, `dev_reset_db.py`, `backup_db.py`

## 🔬 Probe / research (สำรวจ API หรือสมมติฐานก่อน implement — ไม่ใช่ production)

ไฟล์ขึ้นต้น `probe_*`, `_probe_*`, `research_*`, `_research_*`, `scan_*`, `gentle_scan_egp.py` — ทุกไฟล์ในกลุ่มนี้คือ exploration script แบบ throwaway เก็บไว้เป็นหลักฐาน (raw findings มักอยู่คู่กันใน `docs/` หรือ `data/`)

## 🩺 Audit / debug helpers (ไม่ใช่ pipeline, ใช้ตรวจ data manually)

`audit_all_sheets.py`, `audit_pending.py`, `_audit_sent_jobs.py`, `_audit_substring_kw.py`, `count_misaligned.py`, `coverage_audit.py`, `debug_2_jobs.py`, `debug_row_1476.py`, `_diag_egp.py`, `_health_work_kind.py`, `_show_card.py`, `_validate_winrate_tambon.py`, `_verify_2b.py`, `verify_math.py`, `analyze_announce_type.py`, `analyze_center_monitor.py`, `_analyze_bidfield.py`

## 📚 Vocab / classifier curation

`_vocab_approve_batch.py`, `_vocab_approve_batch3.py`, `_vocab_firstpass.py`, `_vocab_prefill_category.py`, `apply_vocab_review.py`, `mine_vocab_gaps.py`

## 🏆 Winner history (legacy build/maintenance, แยกจาก poller ที่รันสด)

`_winner_history_build.py`, `_winner_history_proctype_fix.py`, `_winner_history_reextract.py`, `_winner_history_summary.py`

## 📊 Sheet-specific reports (legacy, Sheets เป็น secondary view ตอนนี้)

`_competitor_share_sheet.py`, `_market_size_sheet.py`, `_my_company_sheet.py`, `_my_company_stats.py`, `_trend_sheet.py`, `_work_type_sheet.py`

## Naming convention

- `Sebastian_*` (PascalCase) — โมดูล pipeline หลักที่ orchestrator เรียกใช้
- `_prefix.py` (underscore) — script ใช้ครั้งเดียว/เฉพาะกิจ ไม่ถูก import จากที่อื่น
- `test_*.py` — pytest
- ไฟล์ snake_case ธรรมดา (ไม่มี prefix) — shared module หรือ standalone tool ที่ใช้ซ้ำ
