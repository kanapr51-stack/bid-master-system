"""
Sebastian_Classifier.py — State Machine Classifier (2026-05-15 redesign)

อ่าน all_jobs (Source of Truth) → clear+rebuild 3 derived sheets:
  active_bidding   → e-bidding ที่ deadline >= วันนี้
  pending_award    → e-bidding ที่ deadline < วันนี้ + ยังไม่ประกาศผู้ชนะ
  awarded_jobs     → e-bidding ที่มี winner data แล้ว

วิธีรัน: python Sebastian_Classifier.py

Bootstrap winner cache:
  ครั้งแรกหลัง redesign — Classifier จะอ่าน data/winner_cache_bootstrap.json
  (สร้างจาก awarded_jobs.json backup ผ่าน scripts/build_winner_cache.py)
  หลังจากนั้น winner data จะอยู่ใน awarded_jobs sheet เอง
"""

import sys
import json
from pathlib import Path
from datetime import datetime, date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SOURCE_SHEET   = "all_jobs"
BOOTSTRAP_FILE = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"

TARGET_PROVINCES = ["นครพนม", "บึงกาฬ"]

# Import DEPT_PROVINCE_MAP from Scraper — ตั้งเป็น single source of truth
try:
    from Sebastian_Scraper import DEPT_PROVINCE_MAP
except ImportError:
    DEPT_PROVINCE_MAP = {}

CONSTRUCTION_INCLUDE = [
    "ถนน", "สะพาน", "ท่อระบาย", "รางระบาย", "ลานคอนกรีต", "ทางเดินคอนกรีต",
    "ฝายคอนกรีต", "ฝาย", "งานโยธา", "ผิวจราจร", "ไหล่ทาง",
    "ปูคอนกรีต", "คสล.", "เสริมผิว", "วางท่อ", "ขุดลอก",
    "ก่อสร้างอาคาร", "ก่อสร้างรั้ว", "กำแพง", "Dowel", "Wire Mesh",
    "คอนกรีตเสริมเหล็ก", "ถมดิน", "ปรับพื้นที่", "คอนกรีตผสมเสร็จ",
    "ระบบประปา", "ประปา",
]
CONSTRUCTION_EXCLUDE = [
    "ซื้อวัสดุ", "ซื้อครุภัณฑ์", "ซื้อจัดซื้อ", "บริการล้าง",
    "ซ่อมแซมรถ", "ซ่อมบำรุงรถ", "บริการซ่อม", "ซ่อมแซมครุภัณฑ์",
    "บริการตรายาง", "บริการเก็บขยะ", "ซื้อเวชภัณฑ์",
    "จัดซื้อครุภัณฑ์", "จัดซื้อรถ",
]


def is_in_target_province(row: dict) -> bool:
    """
    ตรวจว่างานอยู่ในนครพนม/บึงกาฬ — รับมือ 3 case:
      A. province field ระบุจังหวัด (most reliable)
      B. province field ว่าง — fallback ดู title/dept/search_keyword
      C. province field มีค่าแต่ไม่ใช่เป้า — อาจเป็น HQ ทำงานต่างจังหวัด
         ยอมรับเฉพาะถ้า title มี "จ.นครพนม"/"จังหวัดนครพนม"/"จ.บึงกาฬ"/"จังหวัดบึงกาฬ" ชัดเจน
    """
    prov = str(row.get("province", "")).strip()

    # Case A: province ตรง
    if any(p in prov for p in TARGET_PROVINCES):
        return True

    # Case C: province มีค่าแต่ไม่ใช่จังหวัดเป้าหมาย → ต้องการหลักฐานชัดใน title
    # ป้องกัน cross-province false match (เช่น "ตำบลไผ่ล้อม จ.พิษณุโลก")
    if prov:
        title = str(row.get("title", ""))
        for p in TARGET_PROVINCES:
            if f"จ.{p}" in title or f"จังหวัด{p}" in title:
                return True
        return False

    # Case B: province ว่าง — fallback
    text = str(row.get("title", "")) + " " + str(row.get("department", ""))
    if any(p in text for p in TARGET_PROVINCES):
        return True

    # search_keyword ตรงกับ dept/ตำบล ใน DEPT_PROVINCE_MAP
    # (substring เพราะ Scraper อาจเก็บชื่อเต็ม "เทศบาลตำบลศรีสงคราม" ในขณะที่ map key = "ตำบลศรีสงคราม")
    kw = str(row.get("search_keyword", "")).strip()
    if kw:
        for map_key, map_prov in DEPT_PROVINCE_MAP.items():
            if map_key in kw and map_prov in TARGET_PROVINCES:
                return True

    return False


def is_construction_job(title: str) -> bool:
    t = title.lower()
    if any(ex.lower() in t for ex in CONSTRUCTION_EXCLUDE):
        return False
    return any(inc.lower() in t for inc in CONSTRUCTION_INCLUDE)

ALL_JOBS_HEADERS = [
    "job_id", "title", "department", "province", "district", "subdistrict",
    "procurement_type", "budget", "publish_date", "deadline",
    "project_status", "search_keyword", "tor_url",
    "first_seen_at", "last_seen_at",
]

ACTIVE_BIDDING_HEADERS = ALL_JOBS_HEADERS + ["days_remaining"]
PENDING_AWARD_HEADERS  = ALL_JOBS_HEADERS + ["overdue_days"]
AWARDED_JOBS_HEADERS   = ALL_JOBS_HEADERS + ["winner_name", "winner_price", "discount_pct", "award_date"]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_thai_date(s: str):
    """Parse 'dd/mm/yyyy' (พ.ศ. or ค.ศ.) → date object (ค.ศ.)"""
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(s, fmt).date()
            if d.year > 2400:
                d = d.replace(year=d.year - 543)
            return d
        except ValueError:
            continue
    return None


def load_winner_cache() -> dict:
    """รวม winner data จาก 2 source: bootstrap file + awarded_jobs sheet (schema ใหม่)"""
    cache = {}

    if BOOTSTRAP_FILE.exists():
        try:
            data = json.loads(BOOTSTRAP_FILE.read_text(encoding="utf-8"))
            cache.update(data)
            log(f"  bootstrap: {len(data)} winners (จาก {BOOTSTRAP_FILE.name})")
        except Exception as e:
            log(f"  bootstrap load error: {e}")

    try:
        ws = open_sheet(SPREADSHEET_ID, "awarded_jobs")
        rows = ws.get_all_values()
        if rows and len(rows) >= 2:
            headers = rows[0]
            h_idx = {h: i for i, h in enumerate(headers)}
            wn_i = h_idx.get("winner_name", -1)
            jid_i = h_idx.get("job_id", 0)
            wp_i = h_idx.get("winner_price", -1)
            dp_i = h_idx.get("discount_pct", -1)
            ad_i = h_idx.get("award_date", -1)

            sheet_count = 0
            for r in rows[1:]:
                jid = r[jid_i] if jid_i < len(r) else ""
                winner = r[wn_i] if 0 <= wn_i < len(r) else ""
                if jid and winner:
                    cache[jid] = {
                        "winner_name":  winner,
                        "winner_price": r[wp_i] if 0 <= wp_i < len(r) else "",
                        "discount_pct": r[dp_i] if 0 <= dp_i < len(r) else "",
                        "award_date":   r[ad_i] if 0 <= ad_i < len(r) else "",
                    }
                    sheet_count += 1
            log(f"  sheet: {sheet_count} winners (จาก awarded_jobs)")
    except Exception as e:
        log(f"  sheet load error: {e}")

    return cache


def write_sheet(sheet_name: str, headers: list, rows: list):
    ws = open_sheet(SPREADSHEET_ID, sheet_name)
    ws.clear()
    payload = [headers] + rows if rows else [headers]
    ws.update(payload, "A1", value_input_option="USER_ENTERED")
    log(f"  {sheet_name}: {len(rows)} งาน")


def main():
    log("=" * 60)
    log("Sebastian Classifier — state machine (all_jobs source)")
    log("=" * 60)

    log("Loading winner cache...")
    winner_cache = load_winner_cache()
    log(f"  total winners cached: {len(winner_cache)}")

    log(f"\nReading {SOURCE_SHEET}...")
    ws_src = open_sheet(SPREADSHEET_ID, SOURCE_SHEET)
    all_values = ws_src.get_all_values()
    if len(all_values) < 2:
        log(f"❌ {SOURCE_SHEET} ว่าง — abort")
        return

    headers = all_values[0]
    h_idx = {h: i for i, h in enumerate(headers)}

    def g(row, key, default=""):
        i = h_idx.get(key, -1)
        return row[i] if 0 <= i < len(row) else default

    today = date.today()
    log(f"  jobs: {len(all_values) - 1}")
    log(f"  today: {today.isoformat()}")

    active, pending, awarded = [], [], []
    skipped_non_ebid = 0
    skipped_no_jid = 0
    skipped_not_bidding_status = 0
    skipped_off_province = 0
    skipped_non_construction = 0

    for r in all_values[1:]:
        jid = g(r, "job_id")
        if not jid:
            skipped_no_jid += 1
            continue
        if g(r, "procurement_type") != "e-bidding":
            skipped_non_ebid += 1
            continue

        # Build dict view for filter helpers
        row_dict = {h: g(r, h) for h in ALL_JOBS_HEADERS}

        if not is_in_target_province(row_dict):
            skipped_off_province += 1
            continue

        if not is_construction_job(row_dict["title"]):
            skipped_non_construction += 1
            continue

        base = list(r[:len(ALL_JOBS_HEADERS)])
        while len(base) < len(ALL_JOBS_HEADERS):
            base.append("")

        # Has winner from cache → awarded (regardless of project_status)
        if jid in winner_cache:
            wd = winner_cache[jid]
            awarded.append(base + [
                wd.get("winner_name", ""),
                wd.get("winner_price", ""),
                wd.get("discount_pct", ""),
                wd.get("award_date", ""),
            ])
            continue

        proj_status = g(r, "project_status")
        # Skip if not "กำลังประมูล" — these aren't actively biddable
        # (cancelled/extended/ประมูลแล้ว without winner ฯลฯ stay in all_jobs only)
        if proj_status != "กำลังประมูล":
            skipped_not_bidding_status += 1
            continue

        dl = parse_thai_date(g(r, "deadline"))
        if dl is None:
            # eGP says "กำลังประมูล" but deadline missing → active (pessimistic, hope patch_deadlines fills it)
            active.append(base + [""])
        elif dl >= today:
            active.append(base + [str((dl - today).days)])
        else:
            pending.append(base + [str((today - dl).days)])

    log(f"\nClassified:")
    log(f"  active_bidding: {len(active)}")
    log(f"  pending_award:  {len(pending)}")
    log(f"  awarded_jobs:   {len(awarded)}")
    log(f"  skipped non-e-bidding:        {skipped_non_ebid}")
    log(f"  skipped off-province:         {skipped_off_province}")
    log(f"  skipped non-construction:     {skipped_non_construction}")
    log(f"  skipped not 'กำลังประมูล':     {skipped_not_bidding_status}")
    log(f"  skipped no job_id:            {skipped_no_jid}")

    log(f"\nWriting derived sheets (clear+rewrite)...")
    write_sheet("active_bidding", ACTIVE_BIDDING_HEADERS, active)
    write_sheet("pending_award",  PENDING_AWARD_HEADERS,  pending)
    write_sheet("awarded_jobs",   AWARDED_JOBS_HEADERS,   awarded)

    log("\nเสร็จสิ้น")


if __name__ == "__main__":
    main()
