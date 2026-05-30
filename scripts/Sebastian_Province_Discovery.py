"""
Sebastian_Province_Discovery.py — Province-based D0 discovery via eGP announcement search API

ค้นพบ 2026-05-30: endpoint ค้นหาประกาศตามจังหวัด (moiId) เห็นหน่วยงานท้องถิ่น
(อบต./เทศบาล/รพ.สต./โรงเรียน) ที่ RSS มองไม่เห็นเลย

Flow:
  [token harvest ผ่าน Cloudflare Turnstile — ดู memory/project_province_search_api.md]
    → X-Announcement-Token (portable bearer 30 นาที)
  GET announcement?budgetYear=2569&moiId=X&announceType=2&page=N  (announceType=2 = D0)
    → dedupe vs projects_seen → insert (source='province_api', province รู้แน่นอน)
    → notifier เดิม match subscription → queue → enrichment → LINE

Token (เลือกอย่างใดอย่างหนึ่ง):
  --token <value>                      หรือ
  env BMS_ANNOUNCEMENT_TOKEN

Usage:
  python Sebastian_Province_Discovery.py --token <T> --dry-run          # พิสูจน์ ไม่เขียน DB
  python Sebastian_Province_Discovery.py --token <T> --ingest           # เขียน projects_seen
  python Sebastian_Province_Discovery.py --token <T> --filter-amphoe    # กรองเฉพาะ อ.เป้าหมาย
"""

import sys
import os
import time
import json
import argparse
import sqlite3
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(encoding="utf-8")

API = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

# moiId → ชื่อจังหวัด (ที่ตรงกับ subscription_provinces)
PROVINCE_MOI = {
    "480000": "นครพนม",
    "380000": "บึงกาฬ",
}

# อำเภอเป้าหมาย (pilot) — ดู memory/project_target_areas.md
TARGET_AMPHOE = {
    "นครพนม": ["บ้านแพง"],
    "บึงกาฬ": ["บึงโขงหลง"],
}

ANNOUNCE_TYPE_D0 = "2"   # numeric — 2 = D0 (ประกาศเชิญชวน)

TIMEOUT = 15
PAGE_SLEEP = 1.5         # เคารพ rate limit (~100 req / 120s)
COOLDOWN_EVERY = 50      # ทุก 50 req
COOLDOWN_SEC = 30        # พัก 30s (กัน throttle — bug บึงกาฬ 2026-05-30)

_req_count = 0           # นับ req ข้ามทุกจังหวัด (rate limit เป็น global)


def _rate_limit_tick():
    """เรียกหลังทุก request — cooldown ทุก COOLDOWN_EVERY req"""
    global _req_count
    _req_count += 1
    if _req_count % COOLDOWN_EVERY == 0:
        print(f"    ⏳ cooldown {COOLDOWN_SEC}s (req #{_req_count} — กัน rate limit)")
        time.sleep(COOLDOWN_SEC)
    else:
        time.sleep(PAGE_SLEEP)


def _db_path() -> str:
    return os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(token: str, params: dict, path: str = "") -> dict | None:
    url = API + path
    hdrs = {**HEADERS, "X-Announcement-Token": token}
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=TIMEOUT)
        if not r.ok:
            return None
        return r.json()
    except Exception:
        return None


def count_d0(token: str, moi_id: str, budget_year: str) -> tuple[int, int]:
    """คืน (recordsTotal, totalPages) จาก sumProjectMoneyAndCount"""
    body = _get(token, {
        "budgetYear": budget_year, "moiId": moi_id, "announceType": ANNOUNCE_TYPE_D0,
    }, path="/sumProjectMoneyAndCount")
    if not body:
        return -1, -1
    d = body.get("data") or {}
    if d.get("recordsTotal") is None:
        return -1, -1   # token reject / validateCfTurnTile
    return int(d.get("recordsTotal") or 0), int(d.get("totalPages") or 0)


def fetch_page(token: str, moi_id: str, budget_year: str, page: int) -> list[dict]:
    body = _get(token, {
        "budgetYear": budget_year, "moiId": moi_id,
        "announceType": ANNOUNCE_TYPE_D0, "page": str(page),
    })
    if not body:
        return []
    data = body.get("data") or {}
    return data.get("data") or []


def fetch_all_d0(token: str, moi_id: str, budget_year: str) -> list[dict]:
    """ดึงทุกหน้าของจังหวัด — paginate ตาม totalPages"""
    province = PROVINCE_MOI.get(moi_id, moi_id)
    total, pages = count_d0(token, moi_id, budget_year)
    if total < 0:
        print(f"  ❌ {province}: token reject (validateCfTurnTile) — token หมดอายุ/ผิด")
        return []
    print(f"  {province} (moiId={moi_id}): {total} โครงการ / {pages} หน้า")
    out = []
    for p in range(1, pages + 1):
        items = fetch_page(token, moi_id, budget_year, p)
        _rate_limit_tick()
        # empty แต่ยังไม่ถึงปลาย → น่าจะโดน throttle → retry หลัง cooldown
        if not items and len(out) < total:
            print(f"    ⚠️ หน้า {p} ว่าง (น่าจะ throttle) — พัก {COOLDOWN_SEC}s แล้ว retry")
            time.sleep(COOLDOWN_SEC)
            items = fetch_page(token, moi_id, budget_year, p)
            _rate_limit_tick()
        out.extend(items)
        if p % 10 == 0 or p == pages:
            print(f"    หน้า {p}/{pages} — สะสม {len(out)} รายการ")
    return out


def normalize(item: dict, province: str) -> dict:
    return {
        "project_id":   str(item.get("projectId") or ""),
        "announce_type": item.get("announceType") or "D0",
        "province":     province,                       # รู้แน่นอนจาก moiId
        "budget":       int(item.get("projectMoney") or 0),
        "project_name": item.get("projectName") or "",
        "dept_name":    item.get("deptSubName") or "",
        "project_status": item.get("projectStatus") or "",   # A=active, R=cancelled
        "step_id":      item.get("stepId") or "",
        "announce_date": (item.get("announceDate") or "")[:10],
    }


def in_target_amphoe(rec: dict) -> bool:
    """match ชื่ออำเภอเป้าหมายใน project_name หรือ dept_name"""
    amphoes = TARGET_AMPHOE.get(rec["province"], [])
    hay = rec["project_name"] + " " + rec["dept_name"]
    return any(a in hay for a in amphoes)


def ingest(records: list[dict]) -> tuple[int, int]:
    """insert ลง projects_seen (source='province_api'), คืน (new, skipped)"""
    conn = sqlite3.connect(_db_path())
    new = skipped = 0
    now = _utc_now()
    try:
        for r in records:
            if r["project_status"] == "R":   # ยกเลิก — ไม่เก็บ
                continue
            exists = conn.execute(
                "SELECT 1 FROM projects_seen WHERE project_id=?", (r["project_id"],)
            ).fetchone()
            if exists:
                skipped += 1
                continue
            conn.execute("""
                INSERT INTO projects_seen
                  (project_id, announce_type, province, budget, project_name,
                   dept_id, dept_name, extraction_confidence, source, first_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                r["project_id"], r["announce_type"], r["province"], r["budget"],
                r["project_name"], "", r["dept_name"], "hard_province_api",
                "province_api", now,
            ))
            new += 1
        conn.commit()
    finally:
        conn.close()
    return new, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default="", help="ใส่ token ตรงๆ (= ManualProvider)")
    ap.add_argument("--provider", default="", help="manual|chrome9222|playwright (default: env BMS_TOKEN_PROVIDER)")
    ap.add_argument("--moi", action="append", help="moiId (default: ทุกจังหวัดเป้าหมาย)")
    ap.add_argument("--budget-year", default="2569")
    ap.add_argument("--filter-amphoe", action="store_true", help="กรองเฉพาะ อ.เป้าหมาย")
    ap.add_argument("--ingest", action="store_true", help="เขียนลง projects_seen")
    ap.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงาน")
    args = ap.parse_args()

    # token ผ่าน Token Service (single writer) — provider สลับได้โดยไม่แตะ discovery
    from token_service import TokenService, make_provider
    provider = (make_provider("manual", token=args.token) if args.token
                else make_provider(args.provider))
    svc = TokenService(provider)
    token = svc.get_valid_token()
    if not token:
        h = svc.health()
        print(f"❌ ไม่ได้ token (provider={provider.name}, state={h['state']}, err={h.get('last_error')})")
        print("   ใส่ --token <value> หรือ env BMS_ANNOUNCEMENT_TOKEN หรือ --provider chrome9222")
        sys.exit(1)
    print(f"🔑 token OK (provider={svc.health()['provider']}, เหลือ {svc.health()['remaining_sec']}s)")

    moi_ids = args.moi or list(PROVINCE_MOI.keys())
    print(f"🔍 Province Discovery — budgetYear={args.budget_year}, จังหวัด={[PROVINCE_MOI.get(m,m) for m in moi_ids]}")

    all_recs = []
    for moi in moi_ids:
        province = PROVINCE_MOI.get(moi, moi)
        items = fetch_all_d0(token, moi, args.budget_year)
        recs = [normalize(it, province) for it in items]
        all_recs.extend(recs)

    if not all_recs:
        print("\n⚠️ ไม่ได้ข้อมูล — ตรวจ token (อาจหมดอายุ 30 นาที)")
        sys.exit(2)

    active = [r for r in all_recs if r["project_status"] != "R"]
    print(f"\n📊 รวม {len(all_recs)} รายการ ({len(active)} active, {len(all_recs)-len(active)} ยกเลิก)")

    target = [r for r in active if in_target_amphoe(r)]
    print(f"🎯 ในอำเภอเป้าหมาย: {len(target)} รายการ")
    for r in target[:20]:
        print(f"   - {r['project_id']} | {r['dept_name'][:28]:28} | ฿{r['budget']:>12,} | {r['project_name'][:45]}")

    chosen = target if args.filter_amphoe else active
    if args.ingest and not args.dry_run:
        new, skipped = ingest(chosen)
        print(f"\n💾 ingest: +{new} ใหม่, {skipped} มีอยู่แล้ว (source=province_api)")
    else:
        print(f"\n(dry-run — จะ ingest {len(chosen)} รายการ ถ้าใส่ --ingest)")


if __name__ == "__main__":
    main()
