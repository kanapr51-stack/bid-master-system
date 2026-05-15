"""
patch_deadlines.py — ดึง deadline สำหรับ e-bidding "กำลังประมูล" ที่ deadline ว่างใน all_jobs

ขั้นตอน (post 2026-05-15 redesign):
  1. อ่าน all_jobs → หา job_id ที่ project_status="กำลังประมูล" และ deadline ว่าง
  2. เชื่อม Chrome → โหลด process5 (Turnstile)
  3. สำหรับแต่ละ job → ค้นหาตามชื่อหน่วยงาน → click btn-icon → detail page
     → click D0 description → click file_download → อ่าน blob PDF
  4. อัปเดต all_jobs (deadline + last_seen_at)
  5. (auto) เรียก Sebastian_Classifier rebuild active_bidding/pending_award
"""

import sys
import time
import re
import base64
import io
import json
from pathlib import Path
from datetime import datetime, date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet
from playwright.sync_api import sync_playwright

DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SEARCH_URL     = "https://process5.gprocurement.go.th/egp-agpc01-web/announcement"

_DEADLINE_KEYWORDS = [
    "ยื่นข้อเสนอ", "กำหนดยื่น", "เสนอราคา", "ยื่นซอง",
    "ปิดรับ", "สิ้นสุดรับ", "กำหนดส่ง",
]
_THAI_MONTH = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}
_THAI_DATE_RE = re.compile(
    r'(\d{1,2})\s+(' + '|'.join(_THAI_MONTH.keys()) + r')\s+(\d{4})'
)
_NUMERIC_DATE_RE = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')
_THAI_DIGITS_TABLE = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')

_PDF_BLOB_JS = """
async () => {
    const r = await fetch(document.URL);
    const blob = await r.blob();
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject("FileReader error");
        reader.readAsDataURL(blob);
    });
}
"""


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _dept_keyword(dept: str) -> str:
    for prefix in ["องค์การบริหารส่วนตำบล", "เทศบาลตำบล", "เทศบาลเมือง", "เทศบาลนคร"]:
        if dept.startswith(prefix):
            return dept[len(prefix):]
    words = dept.split()
    return words[-1] if words else dept


def _parse_deadline_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pg in pdf.pages:
                text = (pg.extract_text() or "").translate(_THAI_DIGITS_TABLE)
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
                            d = int(m2.group(1))
                            mo = _THAI_MONTH[m2.group(2)]
                            y = m2.group(3)
                            return f"{d:02d}/{mo:02d}/{y}"
    except Exception as e:
        log(f"  PDF parse error: {e}")
    return ""


def fetch_deadline(page, pid: str, search_keyword: str) -> str:
    """
    ดึง deadline จาก PDF ประกาศเชิญชวน:
    1. ค้น search_keyword → หา row index ของ pid จาก API response
    2. คลิก btn-icon → detail page (Angular router)
    3. TABLE4: คลิก description icon ของ ประกาศเชิญชวน → TABLE1 โหลด
    4. TABLE1: คลิก file_download → blob page (new tab)
    5. อ่าน blob → pdfplumber → คืน deadline string
    """
    ctx = page.context
    captured_items = []

    def _on_resp(resp):
        if ("egp-atpj27-service" in resp.url and
                "announcement" in resp.url and
                "sumProject" not in resp.url):
            try:
                body = resp.json()
                items = body.get("data", {}).get("data", [])
                if items:
                    captured_items.extend(items)
            except Exception:
                pass

    page.on("response", _on_resp)

    search_input = None
    for sel in ["input[name*='keyword']", "input[placeholder*='ค้น']", "input[type='search']"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                search_input = el
                break
        except Exception:
            pass

    if not search_input:
        page.remove_listener("response", _on_resp)
        log("  ไม่พบ search input")
        return ""

    search_input.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type(search_keyword, delay=50)
    time.sleep(0.5)

    try:
        with page.expect_response(
            lambda r: ("egp-atpj27-service" in r.url and
                       "announcement" in r.url and
                       "sumProject" not in r.url),
            timeout=20000
        ) as _ri:
            page.locator("button:has-text('ค้นหา')").first.click()
        _ri.value
    except Exception as e:
        log(f"  search error: {e}")
        page.remove_listener("response", _on_resp)
        return ""

    time.sleep(2)
    page.remove_listener("response", _on_resp)

    row_idx = next(
        (i for i, item in enumerate(captured_items)
         if str(item.get("tempProjectId") or item.get("projectId") or "") == pid),
        -1
    )
    if row_idx < 0:
        log(f"  pid {pid} ไม่อยู่ใน '{search_keyword}'")
        return ""

    log(f"  พบที่ row {row_idx}")

    try:
        btns = page.locator("table tbody tr a.btn-icon").all()
        if not btns:
            btns = page.locator("table tbody tr td:last-child a").all()
        if row_idx >= len(btns):
            log(f"  row_idx={row_idx} เกิน len(btns)={len(btns)}")
            return ""
        btns[row_idx].click()
    except Exception as e:
        log(f"  row click error: {e}")
        return ""

    time.sleep(8)

    clicked_t4 = False
    doc_used = ""
    try:
        rows_list = page.locator("table tr").all()
        for target in ["ประกาศเชิญชวน", "ร่างเอกสารประกวดราคา"]:
            for row in rows_list:
                try:
                    rt = row.inner_text(timeout=2000)
                except Exception:
                    continue
                if target in rt:
                    links = row.locator("a").all()
                    if links:
                        links[0].click()
                        clicked_t4 = True
                        doc_used = target
                        break
            if clicked_t4:
                break
    except Exception as e:
        log(f"  TABLE4 error: {e}")

    if not clicked_t4:
        log("  ไม่พบ ประกาศเชิญชวน หรือ ร่างเอกสารประกวดราคา — ข้าม")
        try:
            page.go_back(wait_until="load", timeout=15000)
            time.sleep(2)
        except Exception:
            pass
        return ""
    if doc_used != "ประกาศเชิญชวน":
        log(f"  fallback: ใช้ {doc_used}")

    time.sleep(6)

    deadline = ""
    if doc_used == "ร่างเอกสารประกวดราคา":
        # อ่านวันจาก inline table (ไม่ต้องเปิด PDF)
        try:
            full_text = page.inner_text("body").translate(_THAI_DIGITS_TABLE)
            idx = full_text.find("วันที่สิ้นสุดรับฟังคำวิจารณ์")
            if idx >= 0:
                snippet = full_text[idx:idx+300]
                m = _NUMERIC_DATE_RE.search(snippet)
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
                    deadline = f"{d:02d}/{mo:02d}/{y}"
                else:
                    m2 = _THAI_DATE_RE.search(snippet)
                    if m2:
                        d = int(m2.group(1))
                        mo = _THAI_MONTH[m2.group(2)]
                        y = m2.group(3)
                        deadline = f"{d:02d}/{mo:02d}/{y}"
            if not deadline:
                log("  ไม่พบวันที่สิ้นสุดรับฟังคำวิจารณ์ในตาราง")
        except Exception as e:
            log(f"  inline table read error: {e}")
    else:
        try:
            with ctx.expect_page(timeout=8000) as _npi:
                page.locator("a:has-text('file_download')").first.click()
            pdf_page = _npi.value
            pdf_page.wait_for_load_state("load", timeout=15000)
            time.sleep(2)

            log(f"  PDF URL: {pdf_page.url[:60]}")
            pdf_b64 = pdf_page.evaluate(_PDF_BLOB_JS)
            if pdf_b64:
                pdf_bytes = base64.b64decode(pdf_b64)
                log(f"  PDF {len(pdf_bytes)} bytes")
                deadline = _parse_deadline_from_pdf(pdf_bytes)

            try:
                pdf_page.close()
            except Exception:
                pass

        except Exception as e:
            log(f"  PDF page error: {e}")

    try:
        page.go_back(wait_until="load", timeout=15000)
        time.sleep(2)
    except Exception:
        try:
            page.goto(SEARCH_URL, wait_until="load", timeout=30000)
            time.sleep(3)
        except Exception:
            pass

    return deadline


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
            s_conv = "-".join(parts)
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
    log("=" * 60)
    log("patch_deadlines.py — เริ่มต้น (all_jobs source, post-redesign)")
    log("=" * 60)

    # 1. อ่าน all_jobs → หา jobs ที่ project_status="กำลังประมูล" + deadline ว่าง
    log("อ่าน all_jobs...")
    ws_all = open_sheet(SPREADSHEET_ID, "all_jobs")
    headers = ws_all.row_values(1)
    rows    = ws_all.get_all_records()
    log(f"  พบ {len(rows)} งาน")

    if "deadline" not in headers or "project_status" not in headers:
        log("  ❌ ไม่พบ column 'deadline' หรือ 'project_status' ใน all_jobs")
        return

    dl_col_idx = headers.index("deadline") + 1
    last_seen_col_idx = headers.index("last_seen_at") + 1 if "last_seen_at" in headers else None

    jobs_missing_deadline = [
        r for r in rows
        if str(r.get("project_status", "")).strip() == "กำลังประมูล"
        and not str(r.get("deadline", "")).strip()
        and str(r.get("job_id", "")).strip()
    ]

    log(f"  งานต้อง patch (กำลังประมูล + deadline ว่าง): {len(jobs_missing_deadline)}")

    if not jobs_missing_deadline:
        log("ทุกงานมี deadline แล้ว — เสร็จสิ้น")
        return

    # ดึง deadline ผ่าน Chrome
    results = {}
    if jobs_missing_deadline:
        log(f"\nเชื่อม Chrome ดึง deadline {len(jobs_missing_deadline)} งาน...")
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{DEBUG_PORT}", timeout=5000
                )
            except Exception as e:
                log(f"❌ เชื่อม Chrome ไม่ได้: {e}")
                log("   เปิด Chrome ด้วย: chrome --remote-debugging-port=9222 --user-data-dir=C:\\Temp\\ChromeDebug")
                browser = None

            if browser:
                context = browser.contexts[0]
                page = context.new_page()

                log("โหลด process5 (รอ Turnstile)...")
                page.goto(SEARCH_URL, wait_until="load", timeout=45000)
                time.sleep(8)
                deadline_t = time.time() + 30
                while time.time() < deadline_t:
                    try:
                        btn = page.query_selector("button:has-text('ค้นหา')")
                        if btn and btn.is_enabled():
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                log("session พร้อม")

                for i, row in enumerate(jobs_missing_deadline):
                    pid   = str(row.get("job_id", "")).strip()
                    title = str(row.get("title", ""))[:40]
                    log(f"\n[{i+1}/{len(jobs_missing_deadline)}] {pid} — {title}...")

                    dl = fetch_deadline(page, pid, pid)
                    if dl:
                        results[pid] = dl
                        log(f"  ✅ วันยื่นซอง: {dl}")
                    else:
                        log(f"  ❌ ไม่พบ deadline")

                    if i < len(jobs_missing_deadline) - 1:
                        time.sleep(5)

                page.close()

    if not results:
        log("\nไม่พบ deadline ใหม่ — เสร็จสิ้น")
        return

    log(f"\nพบ deadline ใหม่ {len(results)}/{len(jobs_missing_deadline)} งาน")

    # อัปเดต all_jobs (deadline + last_seen_at)
    log("\nอัปเดต all_jobs...")
    now_iso = datetime.now().isoformat(timespec="seconds")
    all_values = ws_all.get_all_values()
    updates = []

    for row_num, row_vals in enumerate(all_values[1:], start=2):
        job_id = str(row_vals[0]).strip() if row_vals else ""
        if job_id in results:
            updates.append({
                "range": f"all_jobs!{_col_letter(dl_col_idx)}{row_num}",
                "values": [[results[job_id]]],
            })
            if last_seen_col_idx:
                updates.append({
                    "range": f"all_jobs!{_col_letter(last_seen_col_idx)}{row_num}",
                    "values": [[now_iso]],
                })

    if updates:
        ws_all.spreadsheet.values_batch_update(
            {"valueInputOption": "USER_ENTERED", "data": updates}
        )
        log(f"  อัปเดต {len(results)} jobs ใน all_jobs ✅")

    log("\n=== สรุปผล ===")
    for pid, dl in results.items():
        log(f"  {pid}: {dl}")

    # Auto-trigger Classifier rebuild
    log("\nเรียก Classifier rebuild active_bidding/pending_award...")
    try:
        from Sebastian_Classifier import main as classifier_main
        classifier_main()
    except Exception as e:
        log(f"  ⚠️ Classifier error: {e} — รันมือได้: python scripts/Sebastian_Classifier.py")

    log("\nเสร็จสิ้น — รัน Sebastian_LINE_Notify.py เพื่อส่ง LINE")


if __name__ == "__main__":
    main()
