"""
Sebastian_Classifier.py — State Machine Classifier (4-sheet lifecycle, 2026-05-16)

อ่าน all_jobs (Source of Truth) → clear+rebuild 4 derived sheets ตาม lifecycle:
  tor_review       → 'กำลังเตรียม' (รับฟังคำวิจารณ์, ยังไม่เปิดยื่น)
  active_bidding   → 'กำลังประมูล' + deadline >= วันนี้ (ยื่นซองได้ตอนนี้)
  pending_award    → 'กำลังประมูล' deadline ผ่าน, หรือ 'ประมูลแล้ว' ไม่มี winner cache
  awarded_jobs     → มี winner cache แล้ว (ประกาศผู้ชนะ)

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

# Import DEPT_PROVINCE_MAP + FLOW_STATUS_MAP from Scraper — single source of truth
try:
    from Sebastian_Scraper import DEPT_PROVINCE_MAP, FLOW_STATUS_MAP
except ImportError:
    DEPT_PROVINCE_MAP = {}
    FLOW_STATUS_MAP = {}

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

    # Case D: search_keyword ว่าง (data heal pending) — fallback ดู department + subdistrict
    # ครอบคลุม row schema เลื่อน (737 rows) ที่ search_keyword หายไป แต่ dept มี "ตำบลX" ที่อยู่ใน MAP
    dept_sub = str(row.get("department", "")) + " " + str(row.get("subdistrict", ""))
    if dept_sub.strip():
        for map_key, map_prov in DEPT_PROVINCE_MAP.items():
            if map_key in dept_sub and map_prov in TARGET_PROVINCES:
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
    # 2026-05-16: เพิ่มเพื่อรองรับ stepId-driven classifier
    "step_id", "project_status_raw", "announce_type",
]

PRE_TOR_HEADERS        = ALL_JOBS_HEADERS + ["stage_note"]
TOR_REVIEW_HEADERS     = ALL_JOBS_HEADERS + ["stage_note"]
ACTIVE_BIDDING_HEADERS = ALL_JOBS_HEADERS + ["days_remaining"]
PENDING_AWARD_HEADERS  = ALL_JOBS_HEADERS + ["wait_reason"]
# Phase B (2026-05-16): เพิ่ม deliver_day + num_bidders เพื่อ competitive intel
AWARDED_JOBS_HEADERS   = ALL_JOBS_HEADERS + [
    "winner_name", "winner_price", "discount_pct", "award_date",
    "deliver_day", "num_bidders",
]
CANCELLED_JOBS_HEADERS = ALL_JOBS_HEADERS + ["cancel_note"]
# bid_history: 1 row = 1 bidder ต่อ 1 job
BID_HISTORY_HEADERS = [
    "job_id", "bidder_name", "bidder_tin", "price_proposal", "price_agree",
    "result_flag", "is_winner", "is_sme", "is_joint_venture", "jv_partners",
    "consider_desc", "fetched_at",
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _normalize_project_status(raw: str) -> str:
    """
    Resilient mapping → "กำลังประมูล" / "ประมูลแล้ว" / "ยกเลิก" / "กำลังเตรียม" / ""

    รองรับ 3 schema variants ที่หลุดมาจาก migration:
      1. ค่า mapped ตรงๆ ("กำลังประมูล") — return ทันที
      2. raw quantity_note ("province:X | flowName" หรือ "keyword:X | flowName") — extract flowName
      3. stage code ตัวเลข ("0", "1", "4"-"8") — ไม่มี info พอจะ map → return ""
    """
    if not raw:
        return ""
    s = str(raw).strip()

    # Variant 1: mapped value แล้ว
    if s in {"กำลังประมูล", "ประมูลแล้ว", "ยกเลิก", "กำลังเตรียม", "รายงานขอซื้อขอจ้าง"}:
        return s

    # Variant 2: raw quantity_note หลุดมา — แยก " | " แล้ว map flow_name
    if s.startswith("province:") or s.startswith("keyword:"):
        parts = s.split("|", 1)
        if len(parts) == 2:
            flow_name = parts[1].strip()
            return FLOW_STATUS_MAP.get(flow_name, "")

    # Variant 3: ตัวเลข stage code — ไม่มีข้อมูลพอ
    if s.isdigit():
        return ""

    # Unknown — return as-is (อาจเป็น flow_name ตรงๆ)
    return FLOW_STATUS_MAP.get(s, s)


# ================================================================
# 6-Sheet Classifier (stepId-driven) — based on research 2026-05-16
# See: docs/egp_stepid_catalog.md
# ================================================================

# Letter-prefix → sheet (defensive default for unknown stepIds)
LETTER_TO_SHEET = {
    "U": "tor_review",      # U03/U06 = ยังรับฟังคำวิจารณ์
    "M": "active_bidding",  # M03 = ปิดรับฟัง ประกาศแล้ว ⭐ Q7-9 fix
    "S": "active_bidding",  # S01 = เปิดยื่นซองอยู่
    "Z": "active_bidding",  # Z01/Z03 = bidding variants
    "W": "pending_award",   # W01/W03 = รอประกาศผู้ชนะ
    "C": "pending_award",   # C01/C03 = contract stage (มี winner)
    "I": "pending_award",   # I03 = implementation
    "E": "pending_award",   # E03 = re-bid variants
    "X": "pending_award",   # X01/X03 = rare winner variants
    "Q": "pre_tor",         # Q01/Q03 = early prep (Quote stage)
    "B": "cancelled_jobs",  # B01/B03 = cancelled (Block stage)
}


def classify_by_stepid(step_id: str, project_status_raw: str, announce_type: str, has_winner: bool):
    """
    คืน (sheet_name, note_text)
    sheet_name: "tor_review" / "pre_tor" / "active_bidding" / "pending_award" /
                "awarded_jobs" / "cancelled_jobs"
                หรือ None ถ้า skip
    note_text: extra annotation สำหรับ stage_note/cancel_note column
    """
    step = (step_id or "").upper().strip()

    # 1) Cancellation signals (gold + secondary)
    if project_status_raw == "R" or announce_type in ("D1", "W1"):
        # หาจุดที่ยกเลิก
        if step.startswith("B"):
            note = f"ยกเลิกตั้งแต่ต้น ({step})"
        elif step.startswith("M") or step.startswith("U"):
            note = f"ยกเลิกระหว่างเตรียม TOR ({step})"
        elif step.startswith("S") or step.startswith("Z"):
            note = f"ยกเลิกระหว่างยื่นซอง ({step})"
        elif step.startswith(("W", "C", "I", "E", "X")):
            note = f"ยกเลิกหลังประมูล ({step})"
        elif step.startswith("Q"):
            note = f"ยกเลิกตั้งแต่ขั้นวางแผน ({step})"
        else:
            note = f"ยกเลิก ({step or 'ไม่ทราบ stage'})"
        return ("cancelled_jobs", note)

    # 2) มี winner cache → awarded
    if has_winner:
        return ("awarded_jobs", "")

    # 3) ไม่มี stepId → fallback pending
    if not step:
        return ("pending_award", "ไม่ทราบสถานะ (stepId ว่าง)")

    # 4) Letter-prefix routing
    prefix = step[0]
    sheet = LETTER_TO_SHEET.get(prefix)
    if sheet is None:
        # Unknown letter → log warning + fallback pending
        log(f"  ⚠️  Unknown stepId prefix: {step!r} → pending_award (fallback)")
        return ("pending_award", f"ไม่รู้จัก stepId {step}")

    # Note generation
    if sheet == "tor_review":
        note = f"รับฟังคำวิจารณ์ ({step})"
    elif sheet == "pre_tor":
        note = f"ขั้นวางแผน Quote ({step})"
    elif sheet == "active_bidding":
        if prefix == "M":
            note = ""  # active_bidding ใช้ days_remaining column ไม่มี note
        else:
            note = ""
    elif sheet == "pending_award":
        note = f"รอประกาศผู้ชนะ ({step})"
    else:
        note = ""

    return (sheet, note)


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
            skipped_bad = 0
            for r in rows[1:]:
                jid = r[jid_i] if jid_i < len(r) else ""
                winner = r[wn_i] if 0 <= wn_i < len(r) else ""
                if not (jid and winner):
                    continue
                # Skip bad winners (raw quantity_note ที่หลุดมา) — bootstrap file มีข้อมูลถูกต้องแล้ว
                if winner.startswith(("province:", "keyword:")):
                    skipped_bad += 1
                    continue
                cache[jid] = {
                    "winner_name":  winner,
                    "winner_price": r[wp_i] if 0 <= wp_i < len(r) else "",
                    "discount_pct": r[dp_i] if 0 <= dp_i < len(r) else "",
                    "award_date":   r[ad_i] if 0 <= ad_i < len(r) else "",
                }
                sheet_count += 1
            log(f"  sheet: {sheet_count} winners (จาก awarded_jobs)" + (f", skipped {skipped_bad} bad" if skipped_bad else ""))
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

    pre_tor, tor_review, active, pending, awarded, cancelled = [], [], [], [], [], []
    skipped_non_ebid = 0
    skipped_no_jid = 0
    skipped_off_province = 0
    skipped_non_construction = 0
    skipped_unclassified = 0
    used_stepid_path = 0
    used_legacy_path = 0

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

        has_winner = jid in winner_cache
        step_id     = g(r, "step_id")
        ps_raw      = g(r, "project_status_raw")
        announce    = g(r, "announce_type")

        # ── Path A: stepId available → use new stepId-driven classification ──
        if step_id:
            used_stepid_path += 1
            sheet, note = classify_by_stepid(step_id, ps_raw, announce, has_winner)

            if sheet == "cancelled_jobs":
                cancelled.append(base + [note])
                continue
            if sheet == "awarded_jobs":
                wd = winner_cache.get(jid, {})
                awarded.append(base + [
                    wd.get("winner_name", ""),
                    wd.get("winner_price", ""),
                    wd.get("discount_pct", ""),
                    wd.get("award_date", ""),
                ])
                continue
            if sheet == "tor_review":
                tor_review.append(base + [note])
                continue
            if sheet == "pre_tor":
                pre_tor.append(base + [note])
                continue
            if sheet == "active_bidding":
                # ตรวจ deadline เพิ่ม: ถ้า deadline ผ่านแล้ว → ย้ายไป pending
                # (eGP บางครั้งไม่ขยับ stepId จาก M03/S01 → W03 ทันทีหลังวันยื่นซอง)
                dl = parse_thai_date(g(r, "deadline"))
                if dl is None:
                    active.append(base + [""])  # ไม่รู้ deadline → คง active (pessimistic)
                elif dl >= today:
                    active.append(base + [str((dl - today).days)])
                else:
                    # deadline ผ่านแต่ stepId ยังเป็น active → ย้ายไป pending
                    pending.append(base + [f"deadline ผ่าน {(today - dl).days} วัน ({step_id})"])
                continue
            if sheet == "pending_award":
                pending.append(base + [note or "รอประกาศผู้ชนะ"])
                continue
            # sheet is None → skip
            skipped_unclassified += 1
            continue

        # ── Path B: ไม่มี stepId → fallback to legacy text-based logic ──
        used_legacy_path += 1
        if has_winner:
            wd = winner_cache[jid]
            awarded.append(base + [
                wd.get("winner_name", ""), wd.get("winner_price", ""),
                wd.get("discount_pct", ""), wd.get("award_date", ""),
            ])
            continue

        proj_status = _normalize_project_status(g(r, "project_status"))
        if proj_status == "ยกเลิก":
            cancelled.append(base + ["ยกเลิก (legacy)"])
            continue
        if proj_status == "กำลังเตรียม":
            tor_review.append(base + ["รับฟังคำวิจารณ์ (legacy)"])
            continue
        if proj_status == "ประมูลแล้ว":
            pending.append(base + ["รอประกาศผล (legacy)"])
            continue
        if proj_status != "กำลังประมูล":
            skipped_unclassified += 1
            continue

        dl = parse_thai_date(g(r, "deadline"))
        if dl is None:
            active.append(base + [""])
        elif dl >= today:
            active.append(base + [str((dl - today).days)])
        else:
            pending.append(base + [f"deadline ผ่าน {(today - dl).days} วัน"])

    log(f"\nClassified (6-sheet lifecycle):")
    log(f"  🟣 pre_tor        (ขั้นวางแผน Q):       {len(pre_tor)}")
    log(f"  🟢 tor_review     (รับฟังคำวิจารณ์):    {len(tor_review)}")
    log(f"  🔵 active_bidding (ยื่นซองได้):         {len(active)}")
    log(f"  🟡 pending_award  (รอรู้ผู้ชนะ):         {len(pending)}")
    log(f"  ⚪ awarded_jobs   (ประกาศแล้ว):         {len(awarded)}")
    log(f"  ❌ cancelled_jobs (ยกเลิก):              {len(cancelled)}")
    log(f"\nPath usage:")
    log(f"  stepId-driven (Path A): {used_stepid_path}")
    log(f"  legacy text  (Path B):  {used_legacy_path}")
    log(f"\nSkipped:")
    log(f"  non-e-bidding:        {skipped_non_ebid}")
    log(f"  off-province:         {skipped_off_province}")
    log(f"  non-construction:     {skipped_non_construction}")
    log(f"  unclassified status:  {skipped_unclassified}")
    log(f"  no job_id:            {skipped_no_jid}")

    log(f"\nWriting derived sheets (clear+rewrite)...")
    write_sheet("pre_tor",         PRE_TOR_HEADERS,        pre_tor)
    write_sheet("tor_review",      TOR_REVIEW_HEADERS,     tor_review)
    write_sheet("active_bidding",  ACTIVE_BIDDING_HEADERS, active)
    write_sheet("pending_award",   PENDING_AWARD_HEADERS,  pending)
    write_sheet("awarded_jobs",    AWARDED_JOBS_HEADERS,   awarded)
    write_sheet("cancelled_jobs",  CANCELLED_JOBS_HEADERS, cancelled)

    log("\nเสร็จสิ้น")


if __name__ == "__main__":
    main()
