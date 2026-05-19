"""
patch_deadlines.py — ดึง deadline สำหรับ e-bidding "กำลังประมูล" ที่ deadline ว่างใน all_jobs

HTTP-only version (2026-05-19): ไม่ต้องใช้ Chrome
ขั้นตอน:
  1. อ่าน all_jobs → หา jobs stepId M*/S*/Z* ที่ deadline ว่าง
  2. สำหรับแต่ละ job → extract templateId จาก tor_url (RSS link)
  3. ดาวน์โหลด PDF โดยตรงผ่าน process5_http_client
  4. Parse deadline ด้วย pdfplumber
  5. อัปเดต all_jobs (deadline + last_seen_at)
  6. เรียก Classifier rebuild

วิธีใช้:
    python scripts/patch_deadlines.py
    python scripts/patch_deadlines.py --dry-run
    python scripts/patch_deadlines.py --limit 10
"""

import sys
import re
import io
import json
from pathlib import Path
from datetime import datetime, date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from process5_http_client import download_pdf

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"

_DEADLINE_KEYWORDS = [
    "ยื่นข้อเสนอ", "กำหนดยื่น", "เสนอราคา", "ยื่นซอง",
    "ปิดรับซอง", "สิ้นสุดรับซอง", "ปิดรับการเสนอราคา",
    "กำหนดส่ง",
]
_THAI_MONTH = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}
_THAI_DATE_RE  = re.compile(r'(\d{1,2})\s+(' + '|'.join(_THAI_MONTH.keys()) + r')\s+(\d{4})')
_NUMERIC_DATE_RE = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')
_THAI_DIGITS    = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
_TEMPLATE_RE    = re.compile(r'templateId=([A-Za-z0-9\-]+)')


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _parse_deadline_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pg in pdf.pages:
                text = (pg.extract_text() or "").translate(_THAI_DIGITS)
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if any(kw in line for kw in _DEADLINE_KEYWORDS):
                        block = '\n'.join(lines[i:i+4])
                        m = _NUMERIC_DATE_RE.search(block)
                        if m:
                            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
                            return f"{d:02d}/{mo:02d}/{y}"
                        m2 = _THAI_DATE_RE.search(block)
                        if m2:
                            d  = int(m2.group(1))
                            mo = _THAI_MONTH[m2.group(2)]
                            y  = m2.group(3)
                            return f"{d:02d}/{mo:02d}/{y}"
    except Exception as e:
        log(f"  PDF parse error: {e}")
    return ""


def _extract_template_id(tor_url: str) -> str:
    """Extract templateId UUID from tor_url (RSS link or PDF URL)"""
    if not tor_url:
        return ""
    m = _TEMPLATE_RE.search(tor_url)
    return m.group(1) if m else ""


def calc_days_remaining(deadline_str: str) -> str:
    if not deadline_str or str(deadline_str).strip() == "":
        return ""
    s = str(deadline_str).strip()
    formats_to_try = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]
    s_conv = s
    parts = s.replace("/", "-").split("-")
    for i, p in enumerate(parts):
        if len(p) == 4 and int(p) > 2400:
            parts[i] = str(int(p) - 543)
            s_conv   = "-".join(parts)
            formats_to_try = ["%Y-%m-%d", "%d-%m-%Y"] + formats_to_try
            break
    parsed = None
    for fmt in formats_to_try:
        try:
            parsed = datetime.strptime(s_conv, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return ""
    return str((parsed - date.today()).days)


def _col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit",   type=int, default=0)
    args = ap.parse_args()

    log("=" * 60)
    log("patch_deadlines.py — HTTP-only (no Chrome required)")
    log("=" * 60)

    log("อ่าน all_jobs...")
    ws_all  = open_sheet(SPREADSHEET_ID, "all_jobs")
    headers = ws_all.row_values(1)
    rows    = ws_all.get_all_records()
    log(f"  พบ {len(rows)} งาน")

    if "deadline" not in headers:
        log("  ❌ ไม่พบ column 'deadline' ใน all_jobs")
        return

    dl_col_idx       = headers.index("deadline") + 1
    last_seen_col_idx = headers.index("last_seen_at") + 1 if "last_seen_at" in headers else None

    ACTIVE_PREFIXES    = ("M", "S", "Z")
    STALE_YEAR_PREFIXES = ("67", "68")

    def needs_patch(r):
        jid = str(r.get("job_id", "")).strip()
        if not jid or jid[:2] in STALE_YEAR_PREFIXES:
            return False
        if str(r.get("deadline", "")).strip():
            return False
        step   = str(r.get("step_id", "")).strip().upper()
        ps_raw = str(r.get("project_status_raw", "")).strip()
        if step:
            return step[:1] in ACTIVE_PREFIXES and ps_raw != "R"
        return str(r.get("project_status", "")).strip() == "กำลังประมูล"

    jobs_to_patch = [r for r in rows if needs_patch(r)]
    log(f"  ต้อง patch: {len(jobs_to_patch)} งาน")

    if not jobs_to_patch:
        log("ทุกงานมี deadline แล้ว — เสร็จสิ้น")
        return

    if args.limit > 0:
        jobs_to_patch = jobs_to_patch[:args.limit]
        log(f"  --limit: ใช้แค่ {args.limit}")

    # ── Categorize by PDF availability ──
    has_template = [(r, _extract_template_id(str(r.get("tor_url", "")))) for r in jobs_to_patch]
    has_template = [(r, tid) for r, tid in has_template if tid]
    no_template  = [r for r in jobs_to_patch if not _extract_template_id(str(r.get("tor_url", "")))]

    log(f"\n  มี templateId (จาก tor_url): {len(has_template)} งาน")
    log(f"  ไม่มี templateId (เก่า/Chrome): {len(no_template)} งาน")

    if no_template:
        log(f"  ⚠️ {len(no_template)} งานเก่า (ไม่มี RSS link) — ไม่สามารถ patch ด้วย HTTP ได้")
        for r in no_template[:5]:
            log(f"     {r.get('job_id')} | {str(r.get('title',''))[:50]}")

    if args.dry_run:
        log("\n🔍 DRY RUN — ไม่ดาวน์โหลดจริง")
        for r, tid in has_template[:10]:
            log(f"  [DRY] {r.get('job_id')}: templateId={tid[:20]}...")
        return

    if not has_template:
        log("\nไม่มี job ที่มี templateId — เสร็จสิ้น")
        return

    # ── Download PDF + parse deadline ──
    log(f"\nดาวน์โหลด PDF {len(has_template)} งาน...")
    results: dict[str, str] = {}

    for i, (row, template_id) in enumerate(has_template, 1):
        pid   = str(row.get("job_id", "")).strip()
        title = str(row.get("title", ""))[:40]
        log(f"\n[{i}/{len(has_template)}] {pid} — {title}...")
        log(f"  templateId: {template_id}")

        pdf_bytes = download_pdf(template_id)
        if not pdf_bytes:
            log("  ❌ PDF download ล้มเหลว")
            continue

        log(f"  PDF {len(pdf_bytes):,} bytes")
        dl = _parse_deadline_from_pdf(pdf_bytes)
        if dl:
            results[pid] = dl
            log(f"  ✅ วันยื่นซอง: {dl}")
        else:
            log("  ⚠️ parse ไม่เจอ deadline ใน PDF")

    log(f"\nพบ deadline ใหม่ {len(results)}/{len(has_template)} งาน")

    if not results:
        log("ไม่มี deadline ใหม่ — เสร็จสิ้น")
        return

    # ── อัปเดต all_jobs ──
    log("\nอัปเดต all_jobs...")
    now_iso    = datetime.now().isoformat(timespec="seconds")
    all_values = ws_all.get_all_values()
    updates    = []

    for row_num, row_vals in enumerate(all_values[1:], start=2):
        job_id = str(row_vals[0]).strip() if row_vals else ""
        if job_id in results:
            updates.append({
                "range":  f"all_jobs!{_col_letter(dl_col_idx)}{row_num}",
                "values": [[results[job_id]]],
            })
            if last_seen_col_idx:
                updates.append({
                    "range":  f"all_jobs!{_col_letter(last_seen_col_idx)}{row_num}",
                    "values": [[now_iso]],
                })

    if updates:
        ws_all.spreadsheet.values_batch_update(
            {"valueInputOption": "USER_ENTERED", "data": updates}
        )
        log(f"  อัปเดต {len(results)} jobs ✅")

    log("\n=== สรุปผล ===")
    for pid, dl in results.items():
        log(f"  {pid}: {dl}")

    log("\nเรียก Classifier rebuild...")
    try:
        from Sebastian_Classifier import main as classifier_main
        classifier_main()
    except Exception as e:
        log(f"  ⚠️ Classifier error: {e}")

    log("\nเสร็จสิ้น")


if __name__ == "__main__":
    main()
