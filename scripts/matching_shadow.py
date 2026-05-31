"""
matching_shadow.py — รัน matcher บนงานจริง แบบ SHADOW (read-only, ไม่แตะการส่ง)
ดูว่า matcher จะตัดสิน send/cut/soft_include กี่งาน ก่อนเปิดใช้จริง (mode=live ปลอดภัย)

tambon resolution (cheap-first):
  1. dept_name parse (อบต./เทศบาลตำบล → ตำบล) — ฟรี
  2. getProcurementDetail moiName — API (เฉพาะที่ dept_name ไม่บอก)
ผล: tabulate + ตัวอย่างต่อ decision + เขียน data/matching_shadow_log.ndjson

Usage: python matching_shadow.py --limit 30 [--no-api]
"""
import os
import sys
import json
import time
import argparse
import sqlite3
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import job_matcher as jm

DATA = os.environ.get("BMS_DATA_DIR", "/opt/bms/data")
DB = os.path.join(DATA, "bms_customers.db")
SHADOW_LOG = os.path.join(DATA, "matching_shadow_log.ndjson")
PROV = ("นครพนม", "บึงกาฬ")


def tambon_from_dept(dept_name: str) -> str:
    """ตำบลจากชื่อหน่วยงานท้องถิ่น (ฟรี) — อบต./เทศบาลตำบล"""
    d = dept_name or ""
    for pat in ("องค์การบริหารส่วนตำบล", "เทศบาลตำบล"):
        if pat in d:
            return d.split(pat)[-1].strip()
    return ""


def tambon_from_api(project_id: str) -> str:
    """getProcurementDetail moiName (= ตำบลที่ทำงานจริง)"""
    try:
        import process5_http_client as p
        import requests
        tok = p._get_token(project_id)
        h = p.HEADERS_NO_AUTH.copy()
        h["X-Announcement-Token"] = tok
        url = ("https://process5.gprocurement.go.th/egp-atpj27-service/"
               "pb/a-egp-allt-project/announcement/getProcurementDetail")
        d = (requests.get(url, params={"projectId": project_id}, headers=h, timeout=15)
             .json() or {}).get("data") or {}
        return d.get("moiName") or ""
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--no-api", action="store_true", help="ไม่เรียก getProcurementDetail (dept_name อย่างเดียว)")
    args = ap.parse_args()

    cfg = jm.load_config()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT project_id, province, project_name, dept_name FROM projects_seen "
        "WHERE source='province_api' AND province IN ('นครพนม','บึงกาฬ') "
        "ORDER BY first_seen_at DESC LIMIT ?", (args.limit,)).fetchall()
    conn.close()

    stats = Counter()
    src_stats = Counter()
    examples = {"send": [], "cut": [], "soft_include": []}
    out = open(SHADOW_LOG, "w", encoding="utf-8")
    for r in rows:
        tb = tambon_from_dept(r["dept_name"])
        tsrc = "dept_name" if tb else ""
        if not tb and not args.no_api:
            tb = tambon_from_api(r["project_id"])
            tsrc = "api" if tb else ""
            time.sleep(1.0)
        dec, detail = jm.match_job(r["project_name"], r["province"], tb, r["dept_name"], cfg=cfg)
        stats[dec] += 1
        src_stats[detail.get("location_source", tsrc or "none")] += 1
        rec = {"pid": r["project_id"], "decision": dec, "tambon": tb,
               "tambon_src": tsrc, **detail, "name": (r["project_name"] or "")[:50]}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if len(examples[dec]) < 4:
            examples[dec].append(rec)
    out.close()

    print(f"\n=== SHADOW matching ({len(rows)} งานล่าสุด, จังหวัด={PROV}) ===")
    print(f"✅ send={stats['send']}  ❌ cut={stats['cut']}  🟡 soft_include={stats['soft_include']}")
    print(f"location_source: {dict(src_stats)}")
    for dec, ico in (("send", "✅"), ("soft_include", "🟡"), ("cut", "❌")):
        if examples[dec]:
            print(f"\n{ico} {dec} ตัวอย่าง:")
            for e in examples[dec]:
                tail = e.get("label") or e.get("reason") or ""
                print(f"   {e['pid']} | tb={e['tambon'] or '-'}({e['tambon_src'] or '?'}) | {e['name']} | {tail}")
    print(f"\n→ log เต็ม: {SHADOW_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
