"""
cgd_discovery.py — CGD เป็น discovery channel #2 (ทั้งประเทศ)
ค้นหางานใหม่จาก อบต./เทศบาล/โรงพยาบาล/โรงเรียน ที่ RSS ไม่ครอบคลุม

eGP RSS (deptId 101-2511) ครอบคลุมเฉพาะราชการส่วนกลาง
CGD egp-contact-2568 มีสัญญาซื้อจ้างจากทุกหน่วยงาน รวมท้องถิ่น

Architecture: "ingest-once + filter-per-tenant"
  → ดึงทุกจังหวัด เก็บไว้ all_jobs → ลูกค้าแต่ละรายกรองจังหวัดเอง

Quota management (1,000 calls/วัน shared กับ winner_sweep):
  - Early-stop: ถ้าทุก record บนหน้าอยู่ใน seen set แล้ว → หยุด resource นี้
  - Province rotation cursor: quota หมดกลางคัน → บันทึกตำแหน่ง ต่อพรุ่งนี้
  - หลัง first run: daily call ≈ 1-2 calls/resource × provinces ที่มี new records

First run (full backfill): ใช้ quota เยอะ (~300-700 calls)
  รันด้วย --max-calls 800 เพื่อเคลียร์ backlog ใน 1-2 วัน

Args:
  --provinces   จังหวัดเป้าหมาย comma-separated หรือ 'all' (default: all)
  --max-calls   CGD quota ต่อรอบ (default: 600)
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
CURSOR_FILE    = Path(__file__).parent.parent / "data" / "cgd_discovery_cursor.json"

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

ALL_77_PROVINCES = [
    "กระบี่", "กรุงเทพมหานคร", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร",
    "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท",
    "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง",
    "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
    "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส",
    "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์",
    "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พะเยา", "พังงา",
    "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "พระนครศรีอยุธยา", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร",
    "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง",
    "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน",
    "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล",
    "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี",
    "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์",
    "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี",
    "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
]
# กรองซ้ำ (พระนครศรีอยุธยา ซ้ำ) + sort
ALL_77_PROVINCES = sorted(set(ALL_77_PROVINCES))


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Winner extraction ─────────────────────────────────────────────────────────

# Fields ที่รู้แน่ว่าไม่ใช่ชื่อผู้ชนะ — ใช้ exclude ใน column-drift scan
_NON_WINNER_FIELDS = {
    "รหัสโครงการ", "ชื่อโครงการ", "จังหวัด", "เขต/อำเภอ", "ตำบล/แขวง",
    "ชื่อหน่วยงาน", "ชื่อหน่วยงานย่อย", "ชื่อประเภทโครงการ", "วิธีการจัดหา",
    "งบประมาณ(บาท)", "ราคาตกลงซื้อ/จ้าง", "วันที่ประกาศ", "วันที่ลงนามสัญญา",
    "รหัสงบประมาณ", "แหล่งที่มาของเงิน", "ปีงบประมาณ", "_id",
    # Fields เพิ่มเติมจากชุดข้อมูล egp-contact (ป้องกัน column-drift false positive)
    "ลำดับ", "วิธีจัดซื้อฯ", "กลุ่มวิธีจัดซื้อฯ", "วันที่เกิดรายการ",
    "จังหวัด(Eng)", "เขต/อำเภอ(Eng)", "แขวง/ตำบล", "แขวง/ตำบล(Eng)",
    "สถานะโครงการ", "พิกัดของโครงการ", "ลองจิจูดโครงการ",
    "เลขนิติบุคคล", "เลขที่สัญญา", "วันที่สิ้นสุดสัญญา",
    "งบสัญญา(บาท)", "สถานะสัญญา", "ราคากลาง(บาท)",
}

# Fields ที่น่าจะเป็นชื่อผู้ชนะ (priority scan ก่อน)
# ละติจูดโครงการ อยู่ก่อน เพราะ CGD egp-contact มี column drift:
#   ชื่อผู้ชนะ → วันที่สัญญา, ละติจูดโครงการ → ชื่อผู้ชนะจริงๆ
_WINNER_PRIORITY_FIELDS = [
    "ละติจูดโครงการ",
    "ชื่อผู้ชนะ", "ชื่อผู้รับจ้าง", "ชื่อผู้ขาย", "ชื่อบริษัท",
    "ผู้ชนะการเสนอราคา", "ชื่อผู้เสนอราคา",
]


# ต้องมี indicator อย่างน้อย 1 อย่าง ถึงจะถือว่าเป็นชื่อผู้ชนะ
_COMPANY_PATTERN = re.compile(
    r'บริษัท|ห้างหุ้นส่วน|หจก\.|บมจ\.|บจก\.|จำกัด|'
    r'กิจการร่วมค้า|สหกรณ์|มูลนิธิ|สมาคม|วิสาหกิจ|'
    r'นาย\s*[ก-๛]|นาง(?:สาว)?\s*[ก-๛]|'
    r'ร้าน\s*[ก-๛]'  # ร้านค้า/ร้านท้องถิ่น (พบบ่อยใน CGD egp-contact)
)


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
    if re.match(r'^\d{1,2}\s*[฀-๿]', s):
        return False  # ป้องกันวันที่ภาษาไทย เช่น "31 มี.ค. 71"
    if re.fullmatch(r'[\d,.\s]+', s):
        return False
    # ต้องมี company indicator — กัน "วิธีการจัดหา...", "ประกาศเชิญชวน..." ฯลฯ
    return bool(_COMPANY_PATTERN.search(s))


def _extract_winner(rec: dict) -> tuple[str, str, str]:
    """
    Extract (winner_name, winning_price, award_date) แบบ schema-agnostic

    Strategy:
      Pass 1 — ลอง priority field names ที่รู้จัก (fast path)
      Pass 2 — scan ทุก field ที่ไม่ใช่ non-winner → validate ด้วย _is_company_name
               (รองรับ column drift เมื่อ CGD เปลี่ยนชื่อ column)
    """
    winner = ""

    # Pass 1: known winner field names
    for field in _WINNER_PRIORITY_FIELDS:
        if _is_company_name(rec.get(field)):
            winner = str(rec[field]).strip()
            break

    # Pass 2: column-drift fallback — scan all remaining fields
    if not winner:
        for field, val in rec.items():
            if field in _NON_WINNER_FIELDS:
                continue
            if field in _WINNER_PRIORITY_FIELDS:
                continue  # already tried
            if _is_company_name(val):
                winner = str(val).strip()
                break

    price = str(rec.get("ราคาตกลงซื้อ/จ้าง") or "").strip()

    award_date = ""
    # วันที่เกิดรายการ = fallback สำหรับ column-drift records ที่ วันที่ลงนามสัญญา = "ระหว่างดำเนินการ"
    for field in ["วันที่ลงนามสัญญา", "วันที่ตกลงราคา", "วันที่สัญญา", "วันที่เกิดรายการ"]:
        v = str(rec.get(field) or "").strip()
        if v and v != "ระหว่างดำเนินการ" and re.search(r'\d', v):
            award_date = v
            break

    return winner, price, award_date


def _pct(budget_raw, price: str) -> str:
    try:
        b = float(str(budget_raw).replace(",", "").strip())
        p = float(str(price).replace(",", "").strip())
        return f"{((b - p) / b) * 100:.2f}" if b > 0 else ""
    except Exception:
        return ""


# ── CGD API ───────────────────────────────────────────────────────────────────

def _cgd_search(rid: str, province: str, token: str,
                limit: int = 1000, offset: int = 0) -> Optional[dict]:
    params = {
        "resource_id": rid,
        "limit":       limit,
        "offset":      offset,
        "sort":        "_id desc",
        "filters":     json.dumps({"จังหวัด": province}, ensure_ascii=False),
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
        log(f"    ⚠️ CGD HTTP {r.status_code} rid:{rid[:8]} — {r.text[:120]}")
    except Exception as e:
        log(f"    ⚠️ CGD error: {e}")
    return None


def _fetch_new_for_province(province: str, token: str, seen_cgd: set[str],
                             calls_budget: int) -> tuple[list[dict], int]:
    """
    Download CGD records not yet in seen_cgd for province.
    Early-stop when entire page is already in seen_cgd (CGD-processed IDs only —
    NOT all_jobs IDs, so we still fetch winner data for known jobs).
    Returns (new_records_list, calls_used).
    """
    new_records: list[dict] = []
    calls = 0

    for rid in CGD_CONTRACT_RIDS:
        if calls >= calls_budget:
            break
        offset = 0
        rid_new = 0
        while calls < calls_budget:
            data = _cgd_search(rid, province, token, limit=1000, offset=offset)
            calls += 1
            if data is None:
                break
            records = data.get("result", {}).get("records", [])
            if not records:
                break
            total = data.get("result", {}).get("total", 0)

            # Filter: only records NOT yet processed by CGD discovery
            page_new = [r for r in records
                        if str(r.get("รหัสโครงการ", "")).strip() not in seen_cgd]
            new_records.extend(page_new)
            rid_new += len(page_new)

            # Early-stop: ทุก record บนหน้านี้เจอใน seen_cgd แล้ว → หยุดทั้ง resource
            if not page_new:
                break

            offset += len(records)
            if offset >= total:
                break
            time.sleep(0.3)

        # ไม่ log ถ้าไม่มี record ใน resource นี้เลย (ลด noise)
        if rid_new > 0 or offset > 0:
            log(f"    rid:{rid[:8]}…  +{rid_new} new (offset={offset})")

    return new_records, calls


# ── all_jobs row builder ───────────────────────────────────────────────────────

def _build_row(rec: dict, now_iso: str) -> list:
    """CGD record → all_jobs row (26 cols)"""
    jid          = str(rec.get("รหัสโครงการ", "")).strip()
    title        = str(rec.get("ชื่อโครงการ", "")).strip()
    dept_sub     = str(rec.get("ชื่อหน่วยงานย่อย") or rec.get("ชื่อหน่วยงาน", "")).strip()
    province     = str(rec.get("จังหวัด", "")).strip()
    district_raw = str(rec.get("เขต/อำเภอ") or "").strip()
    # district: reject drifted values (coords, status text)
    district = (district_raw
                if district_raw
                and not district_raw.startswith("POINT")
                and not district_raw.startswith("ระหว่าง")
                and not re.fullmatch(r'[\d.\s]+', district_raw)
                else "")
    budget_raw   = rec.get("งบประมาณ(บาท)", "")
    budget       = str(int(budget_raw)) if isinstance(budget_raw, (int, float)) else str(budget_raw).strip()
    publish_date = str(rec.get("วันที่ประกาศ", "")).strip()
    proc_type    = str(rec.get("ชื่อประเภทโครงการ") or "").strip()

    if not province:
        province = extract_province(dept_sub, title)

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
        "",              # deadline
        "ประมูลแล้ว",
        f"keyword:cgd | province:{province}",
        "",              # tor_url
        now_iso,         # first_seen_at
        now_iso,         # last_seen_at
        "",              # step_id
        "",              # project_status_raw
        "",              # announce_type
    ]
    base.extend(tags[col] for col in TAG_COLUMNS)
    return base  # 26 cols


# ── State ─────────────────────────────────────────────────────────────────────

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


def _load_cursor() -> int:
    """Province index ที่ค้างไว้ (สำหรับกรณี quota หมดกลางคัน)"""
    if CURSOR_FILE.exists():
        try:
            return int(json.loads(CURSOR_FILE.read_text(encoding="utf-8")).get("province_offset", 0))
        except Exception:
            pass
    return 0


def _save_cursor(offset: int, total: int):
    CURSOR_FILE.write_text(
        json.dumps({"province_offset": offset % total,
                    "total_provinces": total,
                    "updated": datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8",
    )


def _clear_cursor():
    if CURSOR_FILE.exists():
        CURSOR_FILE.write_text(
            json.dumps({"province_offset": 0, "updated": datetime.now().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )


def _load_winner_cache() -> dict:
    if WINNER_CACHE.exists():
        return json.loads(WINNER_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_winner_cache(cache: dict):
    WINNER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


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
        description="CGD discovery channel — ทั้งประเทศ (ingest-once + filter-per-tenant)")
    ap.add_argument("--provinces", default="all",
                    help="'all' = ทั้ง 77 จังหวัด หรือ comma-separated")
    ap.add_argument("--max-calls", type=int, default=600,
                    help="CGD quota ต่อรอบ (ร่วมกับ winner_sweep 200 = 800/1000 รวม)")
    ap.add_argument("--dry-run", action="store_true",
                    help="รายงานอย่างเดียว ไม่เขียน Sheet")
    args = ap.parse_args()

    _load_env()
    token = os.environ.get("OPEND_USER_TOKEN", "")
    if not token:
        log("❌ OPEND_USER_TOKEN ไม่ set — หยุด")
        return

    if args.provinces.strip().lower() == "all":
        provinces = ALL_77_PROVINCES
    else:
        provinces = [p.strip() for p in args.provinces.split(",") if p.strip()]

    # Resume จาก province ที่ค้างไว้ (ถ้า quota หมดเมื่อวาน)
    start_offset = _load_cursor()
    if start_offset > 0:
        log(f"  ↻ Resume จาก province index {start_offset}/{len(provinces)} (quota หมดรอบก่อน)")
    provinces_ordered = provinces[start_offset:] + provinces[:start_offset]

    log("=" * 60)
    log(f"CGD Discovery — {len(provinces)} จังหวัด (ทั้งประเทศ)")
    log(f"  max-calls={args.max_calls} | dry-run={args.dry_run}")
    log(f"  early-stop: skip resource เมื่อ page เต็มไปด้วย seen IDs")
    log("=" * 60)

    ws_all = open_sheet(SPREADSHEET_ID, "all_jobs")
    rows = ws_all.get_all_values()
    known_ids: set[str] = {r[0].strip() for r in rows[1:] if r and r[0].strip()}
    log(f"  all_jobs: {len(known_ids)} jobs known")

    seen_cgd     = _load_seen()
    winner_cache = _load_winner_cache()
    log(f"  cgd seen: {len(seen_cgd)} | winner_cache: {len(winner_cache)}")

    calls_left       = args.max_calls
    new_rows: list[list] = []
    total_new_jobs   = 0
    total_new_winners = 0
    now_iso          = datetime.now().isoformat(timespec="seconds")
    provinces_done   = 0

    for prov_idx, province in enumerate(provinces_ordered):
        if calls_left <= 0:
            remaining = len(provinces_ordered) - prov_idx
            real_offset = (start_offset + prov_idx) % len(provinces)
            _save_cursor(real_offset, len(provinces))
            log(f"\n⏸ quota หมด ({args.max_calls} calls) — บันทึก cursor ที่ {province} "
                f"(index {real_offset}) | {remaining} จังหวัดเหลือ → ต่อพรุ่งนี้")
            break

        # Early-stop ใช้เฉพาะ seen_cgd (CGD-processed IDs) —
        # ไม่รวม known_ids เพื่อให้ดึง winner data สำหรับ jobs ที่อยู่ใน all_jobs แล้ว
        new_records, calls = _fetch_new_for_province(province, token, seen_cgd, calls_left)
        calls_left -= calls
        provinces_done += 1

        if not new_records:
            continue  # ไม่มีใหม่ — ข้าม (ไม่ log เพื่อลด noise)

        log(f"  [{province}] +{len(new_records)} CGD records | calls {calls} (เหลือ {calls_left})")

        for rec in new_records:
            pid = str(rec.get("รหัสโครงการ", "")).strip()
            if not pid:
                continue

            # Winner cache update สำหรับ ทุก record (รวมถึง jobs ที่อยู่ใน all_jobs แล้ว)
            winner_name, winner_price, award_date = _extract_winner(rec)
            budget_raw = rec.get("งบประมาณ(บาท)", "")
            if winner_name and pid not in winner_cache:
                winner_cache[pid] = {
                    "winner_name":  winner_name,
                    "winner_price": winner_price,
                    "discount_pct": _pct(budget_raw, winner_price),
                    "award_date":   award_date,
                }
                total_new_winners += 1

            seen_cgd.add(pid)

            # Discovery: append ถ้าไม่เคยอยู่ใน all_jobs
            if pid in known_ids:
                continue

            row = _build_row(rec, now_iso)
            new_rows.append(row)
            known_ids.add(pid)
            total_new_jobs += 1
    else:
        # Loop เสร็จโดยไม่โดน quota — reset cursor
        _clear_cursor()

    log(f"\n── Summary ──────────────────────────────────────")
    log(f"  Provinces scanned  : {provinces_done}/{len(provinces)}")
    log(f"  New jobs discovered: {total_new_jobs}")
    log(f"  New winner updates : {total_new_winners}")
    log(f"  CGD calls used     : {args.max_calls - calls_left}")
    log(f"  dry-run            : {args.dry_run}")

    if args.dry_run:
        if new_rows:
            log("\n  ตัวอย่าง 5 rows แรก:")
            for row in new_rows[:5]:
                log(f"    {row[0]} | {row[3]} | {row[1][:50]}")
        return

    if total_new_winners > 0:
        _save_winner_cache(winner_cache)
        log(f"\n✅ winner_cache +{total_new_winners} (รวม {len(winner_cache)})")

    if new_rows:
        log(f"\nAppending {len(new_rows)} rows to all_jobs...")
        CHUNK = 500
        for i in range(0, len(new_rows), CHUNK):
            ws_all.append_rows(new_rows[i:i + CHUNK], value_input_option="RAW")
            log(f"  {min(i + CHUNK, len(new_rows))}/{len(new_rows)} rows written")
            time.sleep(1)
        log("✅ append เสร็จ")

    _save_seen(seen_cgd)
    log(f"✅ seen set อัปเดต ({len(seen_cgd)} ids)")

    log(f"\n✅ CGD Discovery เสร็จ | +{total_new_jobs} jobs | +{total_new_winners} winners")


if __name__ == "__main__":
    main()
