"""test_runtime_paths.py — กัน regression: runtime-state ต้องผ่าน bms_paths ไม่ hardcode app/data."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

RUNTIME_FILES = [
    "rss_queue.json", "rss_seen_ids.json", "api_ingestion_state.json",
    "resolve_heartbeat.json", "resolve_plane_state.json", "rss_stage_rotation.json",
    "rss_notifier_epoch.txt", "dept_failure_state.json", "seen_ids.json",
]
# ไฟล์ที่ migrate แล้ว (active runtime-state writers/readers)
MIGRATED = [
    "scripts/Sebastian_RSS_Scraper.py", "scripts/Sebastian_RSS_Notifier.py",
    "scripts/Sebastian_Enrichment_Worker.py", "scripts/health_deadman.py",
    "scripts/queue_health.py", "scripts/pipeline_funnel.py",
    "scripts/dashboard_extractor.py", "scripts/refresh_active_jobs.py",
]
BAD = re.compile(r'parent\.parent\s*/\s*["\']data["\']\s*/\s*["\']([^"\']+)["\']')
ROOT = Path(__file__).parent.parent
fails = []
for rel in MIGRATED:
    p = ROOT / rel
    if not p.exists():
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        m = BAD.search(line)
        if m and m.group(1) in RUNTIME_FILES:
            fails.append(f"{rel}:{i} ยัง hardcode app/data → {m.group(1)}")
if fails:
    print("❌ FAIL:"); [print("  " + f) for f in fails]; sys.exit(1)
print(f"✅ PASS {len(MIGRATED)} scripts ใช้ bms_paths สำหรับ runtime-state")
