"""
cgd_discovery.py — CGD เป็น discovery channel #2
ค้นหางานใหม่จาก อบต./เทศบาล/โรงพยาบาล/โรงเรียน ที่ RSS ไม่ครอบคลุม

eGP RSS (deptId 101-2511) ครอบคลุมเฉพาะราชการส่วนกลาง
CGD egp-contact-2568 มีสัญญาซื้อจ้างจากทุกหน่วยงาน รวมท้องถิ่น (อบต./เทศบาล/โรงพยาบาล)

Flow:
  1. Download CGD records สำหรับ target provinces (all 10 resource files, paginate)
  2. Delta: projectIds ที่ไม่อยู่ใน all_jobs sheet
  3. Build row สำหรับ new jobs ใช้ข้อมูล CGD โดยตรง (ไม่เรียก eGP API)
  4. Append to all_jobs sheet
  5. Update winner_cache for new awarded jobs

CGD = signed contracts เท่านั้น → project_status = "ประมูลแล้ว" ทุก row
Classifier เติม tag fields ใน step ถัดไป (Sebastian_Classifier.py)

Args:
  --provinces   จังหวัดเป้าหมาย comma-separated (default: นครพนม,บึงกาฬ)
  --max-calls   CGD quota ต่อรอบ (default: 400, quota รวม 1000/วัน)
  --dry-run     รายงานอย่างเดียว ไม่เขียน Sheet
"""

import os
import sys
import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

import requests
from sheets_client import open_sheet
from classifier_tags import classify_all, TAG_COLUMNS
from province_extractor import extract_province

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
WINNER_CACHE   = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
SEEN_FILE      = Path(__file__).parent.parent / "data" / "cgd_discovery_seen.json"

CKAN_BASE = "https://opend.data.go.th/get-ckan"
CGD_CONTRACT_RIDS = [
    "e4eaa1b4-eb1a-4534-b227-988ee25b898d",
    "9ae119c4-73b9-4bb6-9b71-7b355269bc00",
    "1c1a90af-2d47-4bfb-ae87-e479b2582257",
    "c2385bd6-7e2a-40c2-94d8-6a65824c9415",
    "bb538ac1-3455-446d-b975-d709d6439e72",
    "5b98d6ba-0f66-4bb1-b8db-9b9aae928171",
    "037adcca-b349-44f6-9686-9fd1e9182227",
    "26316135-a95f-40e3-b2e8-1c912046c0ed",
    "882332c4-1f60-4db7-9962-9062eb08f6c4",
    "35961821-d945-4fc0-8ce1-a96b4cd46bd6",
]

DEFAULT_PROVINCES = ["นครพนม", "บึงกาฬ"]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Winner extraction (shared logic with winner_sweep.py) ─────────────────────

def _is_company_name(val) -> bool:
    if not val or not isinstance(val, str):
        return False
    s = str(val).strip()
    if not s or len(s) < 4:
        return False
    if s.startswith("POINT") or s.startswith("ระหว่าง"):
        return False
    if not re.search(r'[฀-๿]', s):
        return False
    if re.match(r'^\d{1,2}\s*[฀-๿]', s):   # Thai date
        return False
    if re.fullmatch(r'[\d,.\s]+', s):          # pure number
        return False
    return True


def _extract_winner(rec: dict) -> tuple[str, str, str]:
    """Extract (winner_name, winning_price, award_date) รองรับ column drift"""
    winner = ""
    for field in ["ละติจูดโครงการ", "ชื่อผู้ชนะ", "เลขนิติบุคคล", "ลองจิจูดโครงการ"]:
        if _is_company_name(rec.get(field)):
            winner = str(rec[field]).strip()
            break

    price = str(rec.get("ราคาตกลงซื้อ/จ้าง") or "").strip()
    budget = str(rec.get("งบประมาณ(บาท)") or "").strip()

    award_date = ""
    for field in ["เลขนิติบุคคล", "วันที่ลงนามสัญญา"]:
        v = str(rec.get(field) or "").strip()
        if v and re.search(r'\d', v) and re.search(r'[฀-๿]', v):
            award_date = v
            break

    return winner, price, award_date


def _pct(budget: str, price: str) -> str:
    try:
        b = float(str(budget).replace(",", "").strip())
        p = float(str(price).replace(",", "").strip())
        return f"{((b - p) / b) * 100:.2f}" if b > 0 else ""
    except Exception:
        return ""


# ── CGD API ───────────────────────────────────────────────────────────────────

def _cgd_search(rid: str, province: str, token: str,
                limit: int = 1000, offset: int = 0) -> Optional[dict]:
    params = {
        "resource_id": rid,
        "limit": limit,
        "offset": offset,
        "filters": json.dumps({"จังหวัด": province}),
    }
    try:
        r = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params=params,
            headers={"api-key": token, "Accept": "application/json"},
            timeout=30,
        )
        if r.ok:
            return r.json()
    except Exception as e:
        log(f"    ⚠️ CGD request error: {e}")
    return None


def _fetch_province_records(province: str, token: str,
                             max_calls: int) -> tuple[list[dict], int]:
    """
    Download all CGD records for province across all 10 resource files.
    Returns (records_list, calls_used).
    """
    all_records: list[dict] = []
    calls = 0

    for rid in CGD_CONTRACT_RIDS:
        if calls >= max_calls:
            log(f"  ⚠️ quota หมด ({calls}/{max_calls}) — หยุดที่ resource {rid[:8]}...")
            break
        offset = 0
        rid_count = 0
        while calls < max_calls:
            data = _cgd_search(rid, province, token, limit=1000, offset=offset)
            calls += 1
            if data is None:
                break
            records = data.get("result", {}).get("records", [])
            if not records:
                break
            total = data.get("result", {}).get("total", 0)
            all_records.extend(records)
            rid_count += len(records)
            offset += len(records)
            if offset >= total:
                break
            time.sleep(0.3)  # gentle rate-limit

        if rid_count > 0:
            log(f"    resource {rid[:8]}…: {rid_count} records")

    return all_records, calls


# ── all_jobs sheet ────────────────────────────────────────────────────────────

def _load_known_ids(ws) -> set[str]:
    """Read all projectIds already in all_jobs"""
    rows = ws.get_all_values()
    return {r[0].strip() for r in rows[1:] if r and r[0].strip()}, rows[0]


def _build_row(rec: dict, now_iso: str) -> list:
    """
    CGD record → all_jobs row (26 cols)
    project_status = "ประมูลแล้ว" เสมอ (CGD = signed contracts)
    step_id / deadline / tor_url = '' (ไม่รู้จาก CGD)
    """
    jid            = str(rec.get("รหัสโครงการ", "")).strip()
    title          = str(rec.get("ชื่อโครงการ", "")).strip()
    dept_sub       = str(rec.get("ชื่อหน่วยงานย่อย") or rec.get("ชื่อหน่วยงาน", "")).strip()
    province       = str(rec.get("จังหวัด", "")).strip()
    district_raw   = str(rec.get("เขต/อำเภอ") or "").strip()
    # district อาจ drift หรือไม่ → ตรวจว่าเป็นชื่ออำเภอจริงหรือเปล่า
    district       = district_raw if (district_raw and not district_raw.startswith("POINT")
                                      and not district_raw.startswith("ระหว่าง")
                                      and not re.fullmatch(r'[\d.\s]+', district_raw)) else ""
    budget_raw     = rec.get("งบประมาณ(บาท)", "")
    budget         = str(int(budget_raw)) if isinstance(budget_raw, (int, float)) else str(budget_raw).strip()
    publish_date   = str(rec.get("วันที่ประกาศ", "")).strip()
    proc_type      = str(rec.get("ชื่อประเภทโครงการ") or "").strip()

    # Province: CGD มีให้แล้ว แต่ตรวจสอบด้วย extractor ถ้าว่าง
    if not province:
        province = extract_province(dept_sub, title)

    dept_note = f"keyword:cgd | province:{province}"

    row_dict = {
        "title":            title,
        "procurement_type": proc_type,
        "budget":           budget,
        "deadline":         "",
        "province":         province,
        "district":         district,
        "subdistrict":      "",
        "announce_type":    "",
    }
    tags = classify_all(row_dict)

    base = [
        jid,
        title,
        dept_sub,
        province,
        district,
        "",              # subdistrict
        proc_type,
        budget,
        publish_date,
        "",              # deadline (ไม่รู้จาก CGD)
        "ประมูลแล้ว",     # project_status
        dept_note,
        "",              # tor_url
        now_iso,         # first_seen_at
        now_iso,         # last_seen_at
        "",              # step_id (ไม่รู้จาก CGD)
        "",              # project_status_raw
        "",              # announce_type
    ]
    base.extend(tags[col] for col in TAG_COLUMNS)
    return base   # 26 cols


# ── Cache & state ─────────────────────────────────────────────────────────────

def _load_winner_cache() -> dict:
    if WINNER_CACHE.exists():
        return json.loads(WINNER_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_winner_cache(cache: dict):
    WINNER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")).get("ids", []))
        except Exception:
            pass
    return set()


def _save_seen(seen: set[str]):
    SEEN_FILE.write_text(
        json.dumps({"ids": sorted(seen),
                    "count": len(seen),
                    "updated": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def _load_env():
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="CGD discovery channel — เพิ่ม local govt jobs ที่ RSS พลาด")
    ap.add_argument("--provinces", default=",".join(DEFAULT_PROVINCES),
                    help=f"จังหวัดเป้าหมาย comma-separated (default: {','.join(DEFAULT_PROVINCES)})")
    ap.add_argument("--max-calls", type=int, default=400,
                    help="CGD API quota ต่อรอบ (quota รวม 1000/วัน, winner_sweep ใช้ 200)")
    ap.add_argument("--dry-run", action="store_true",
                    help="รายงานอย่างเดียว ไม่เขียน Sheet")
    args = ap.parse_args()

    _load_env()
    token = os.environ.get("OPEND_USER_TOKEN", "")
    if not token:
        log("❌ OPEND_USER_TOKEN ไม่ set — หยุด")
        return

    provinces = [p.strip() for p in args.provinces.split(",") if p.strip()]
    log("=" * 60)
    log(f"CGD Discovery — provinces: {provinces}")
    log(f"  max-calls={args.max_calls} | dry-run={args.dry_run}")
    log("=" * 60)

    # ── โหลด all_jobs ──
    log("Reading all_jobs sheet...")
    ws_all = open_sheet(SPREADSHEET_ID, "all_jobs")
    known_ids, headers = _load_known_ids(ws_all)
    log(f"  all_jobs: {len(known_ids)} jobs known")

    # ── โหลด seen set (CGD-specific — หลีกเลี่ยง re-process ที่ CGD ดาวน์โหลดแล้ว) ──
    seen_cgd = _load_seen()
    log(f"  cgd_discovery_seen: {len(seen_cgd)} ids processed before")

    winner_cache = _load_winner_cache()
    log(f"  winner_cache: {len(winner_cache)} known winners")

    # ── Download + delta per province ──
    total_new_jobs   = 0
    total_new_winners = 0
    calls_used_total  = 0
    calls_left        = args.max_calls
    new_rows: list[list] = []
    now_iso = datetime.now().isoformat(timespec="seconds")

    for province in provinces:
        if calls_left <= 0:
            log(f"  ⚠️ quota หมด — ข้าม {province}")
            continue

        log(f"\n[{province}] Downloading CGD records...")
        records, calls = _fetch_province_records(province, token, calls_left)
        calls_left       -= calls
        calls_used_total += calls
        log(f"  → {len(records)} records | used {calls} calls (เหลือ {calls_left})")

        prov_new = 0
        prov_new_winners = 0
        for rec in records:
            pid = str(rec.get("รหัสโครงการ", "")).strip()
            if not pid:
                continue

            # Winner extraction สำหรับทุก record (ไม่ว่าจะ new หรือเก่า)
            winner_name, winner_price, award_date = _extract_winner(rec)
            budget_raw = rec.get("งบประมาณ(บาท)", "")
            budget_str = str(int(budget_raw)) if isinstance(budget_raw, (int, float)) else str(budget_raw)

            if winner_name and pid not in winner_cache:
                winner_cache[pid] = {
                    "winner_name":  winner_name,
                    "winner_price": winner_price,
                    "discount_pct": _pct(budget_str, winner_price),
                    "award_date":   award_date,
                }
                prov_new_winners += 1

            # Discovery: เพิ่ม job ใหม่ที่ไม่เคยอยู่ใน all_jobs
            if pid in known_ids or pid in seen_cgd:
                continue

            row = _build_row(rec, now_iso)
            new_rows.append(row)
            known_ids.add(pid)    # ป้องกัน duplicate ใน batch เดียวกัน
            seen_cgd.add(pid)
            prov_new += 1

        log(f"  {province}: +{prov_new} new jobs | +{prov_new_winners} new winners in cache")
        total_new_jobs    += prov_new
        total_new_winners += prov_new_winners

    log(f"\n── Summary ──────────────────────────────")
    log(f"  Total new jobs to append : {total_new_jobs}")
    log(f"  Total new winner updates : {total_new_winners}")
    log(f"  CGD calls used           : {calls_used_total}")
    log(f"  dry-run                  : {args.dry_run}")

    if args.dry_run:
        if new_rows:
            log("\n  ตัวอย่าง 5 rows แรก:")
            for row in new_rows[:5]:
                log(f"    {row[0]} | {row[3]} | {row[1][:50]}")
        return

    # ── เขียน winner_cache ──
    if total_new_winners > 0:
        _save_winner_cache(winner_cache)
        log(f"\n✅ winner_cache อัปเดต +{total_new_winners} (รวม {len(winner_cache)})")

    # ── Append new rows ──
    if new_rows:
        log(f"\nAppending {len(new_rows)} rows to all_jobs...")
        CHUNK = 500
        for i in range(0, len(new_rows), CHUNK):
            chunk = new_rows[i:i + CHUNK]
            ws_all.append_rows(chunk, value_input_option="RAW")
            log(f"  เขียนแล้ว {min(i + CHUNK, len(new_rows))}/{len(new_rows)}")
            time.sleep(1)
        log(f"✅ append เสร็จ")

    # ── Save seen set ──
    _save_seen(seen_cgd)
    log(f"✅ cgd_discovery_seen อัปเดต ({len(seen_cgd)} ids)")

    log(f"\n✅ CGD Discovery เสร็จ | +{total_new_jobs} jobs | +{total_new_winners} winners")


if __name__ == "__main__":
    main()
