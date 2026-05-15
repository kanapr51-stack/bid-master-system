"""
Sebastian_Doc_Downloader.py — ดาวน์โหลด BOQ zip จาก gprocurement → แตก PDF
อ่านงานใหม่จาก Sheet 1 → ดาวน์โหลด zip ผ่าน Chrome CDP → แตก pB*.pdf

วิธีใช้:
    1. Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
    2. python Sebastian_Doc_Downloader.py
"""

import sys
import time
import json
import base64
import zipfile
import io
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

# ---- CONFIG ----
DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET1_NAME    = "active_bidding"
DOWNLOAD_DIR   = Path(__file__).parent.parent / "downloads"

PROCESS5_BASE     = "https://process5.gprocurement.go.th"
SEARCH_URL        = f"{PROCESS5_BASE}/egp-agpc01-web/announcement"
BOQ_LIST_URL      = f"{PROCESS5_BASE}/egp-project-service/listProjectPriceBuildZipByProjectId"
DOWNLOAD_FILE_URL = f"{PROCESS5_BASE}/egp-upload-service/v1/downloadFileTest"
BOQ_APIKEY        = "Liaqv30xLpFGOlJPW1N0hPKJkbO7vWUS"



def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ================================================================
# SHEETS
# ================================================================

def get_sheet1():
    sys.path.insert(0, str(Path(__file__).parent))
    from sheets_client import open_sheet
    return open_sheet(SPREADSHEET_ID, SHEET1_NAME)


def read_new_jobs(max_jobs: int = 0) -> list[dict]:
    """อ่านงาน status='new' จาก raw_jobs_bidding (e-bidding กำลังประมูล เท่านั้น)"""
    ws = get_sheet1()
    rows = ws.get_all_records()
    jobs = []
    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        if status == "new":
            jobs.append(row)
        if max_jobs and len(jobs) >= max_jobs:
            break
    return jobs


def update_job_status(job_id: str, new_status: str):
    ws = get_sheet1()
    cell = ws.find(job_id, in_column=1)
    if cell:
        ws.update_cell(cell.row, ws.find("status", in_row=1).col, new_status)


def update_tor_url(job_id: str, tor_url: str):
    """บันทึก tor_url ลง raw_jobs_bidding — สร้างคอลัมน์ถ้ายังไม่มี"""
    import urllib.parse
    ws = get_sheet1()
    headers = ws.row_values(1)
    if "tor_url" not in headers:
        tor_col = len(headers) + 1
        ws.update_cell(1, tor_col, "tor_url")
    else:
        tor_col = headers.index("tor_url") + 1
    cell = ws.find(job_id, in_column=1)
    if cell:
        ws.update_cell(cell.row, tor_col, tor_url)


# ================================================================
# BROWSER
# ================================================================

def connect_browser(p):
    for attempt in range(15):
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
            log("เชื่อมต่อ Chrome สำเร็จ")
            return browser
        except Exception:
            log(f"  รอ Chrome... ({attempt+1}/15)")
            time.sleep(2)
    raise RuntimeError("เชื่อมต่อ Chrome ไม่ได้ — เปิด Chrome ด้วย --remote-debugging-port=9222")


def new_page(browser):
    context = browser.contexts[0]
    return context.new_page()


def ensure_on_process5(page):
    if "process5.gprocurement.go.th" not in page.url:
        log("  navigate ไป process5...")
        page.goto(SEARCH_URL, wait_until="load", timeout=45000)
        time.sleep(5)


# ================================================================
# BOQ DOWNLOAD (2-step flow)
# ================================================================

def check_cancelled(page, project_id: str) -> bool:
    """
    ตรวจสอบว่างานถูกยกเลิกหรือไม่ ผ่าน greenBook API
    คืนค่า True ถ้ามี announceType=D1 (ยกเลิกประกาศเชิญชวน)
    """
    url = f"{PROCESS5_BASE}/egp-atpj27-service/pb/a-egp-allt-project/announcement/greenBook?mode=LINK&methodId=16&tempProjectId={project_id}&pageAnnounceType=D1"
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{credentials: 'include'}});
            return await r.json();
        }} catch(e) {{ return {{error: e.toString()}}; }}
    }}"""
    try:
        data = page.evaluate(js)
        items = data.get("data", {}).get("greenBookAnnouncementTypeLinkDto", []) or []
        for item in items:
            if item.get("announceType") == "D1" and item.get("announceFlag") == "D":
                log(f"  ยกเลิกแล้ว (D1/D): {item.get('announceTypeDesc', '')}")
                return True
        return False
    except Exception as e:
        log(f"  check_cancelled error: {e}")
        return False


def get_boq_zip_id(page, project_id: str) -> str | None:
    """
    Step 1: ดึง zipFileId จาก listProjectPriceBuildZipByProjectId
    ต้องการ header apikey และ browser session cookies
    """
    url = f"{BOQ_LIST_URL}?projectId={project_id}"
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{
                credentials: 'include',
                headers: {{'apikey': '{BOQ_APIKEY}', 'Accept': 'application/json'}}
            }});
            return await r.json();
        }} catch(e) {{ return {{error: e.toString()}}; }}
    }}"""
    try:
        data = page.evaluate(js)
        if data.get("error"):
            log(f"  BOQ list error: {data['error']}")
            return None
        items = data.get("data", [])
        if not items:
            log("  ไม่มี BOQ zip สำหรับงานนี้")
            return None
        zip_id = items[0].get("zipFileId")
        zip_name = items[0].get("priceBuildName", "")
        log(f"  zipFileId: {zip_id} ({zip_name})")
        return zip_id
    except Exception as e:
        log(f"  get_boq_zip_id error: {e}")
        return None


def download_boq_zip(page, zip_file_id: str) -> bytes | None:
    """
    Step 2: ดาวน์โหลด BOQ zip เป็น bytes ผ่าน browser fetch (ArrayBuffer → base64)
    ไม่ต้องการ apikey — ใช้แค่ session cookies
    """
    url = f"{DOWNLOAD_FILE_URL}?fileId={zip_file_id}"
    js = f"""async () => {{
        try {{
            const r = await fetch({json.dumps(url)}, {{credentials: 'include'}});
            if (!r.ok) return {{error: r.status}};
            const buf = await r.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let b = '';
            for (let i = 0; i < bytes.byteLength; i++) b += String.fromCharCode(bytes[i]);
            return {{status: r.status, size: buf.byteLength, b64: btoa(b)}};
        }} catch(e) {{ return {{error: e.toString()}}; }}
    }}"""
    try:
        res = page.evaluate(js)
        if res.get("error"):
            log(f"  download error: {res['error']}")
            return None
        size = res.get("size", 0)
        log(f"  ดาวน์โหลด zip: {size:,} bytes")
        if not res.get("b64"):
            return None
        return base64.b64decode(res["b64"])
    except Exception as e:
        log(f"  download_boq_zip error: {e}")
        return None


def extract_zip_pdfs(zip_bytes: bytes, job_dir: Path) -> dict:
    """
    แตก PDF จาก zip → job_dir/
    คืนค่า {"pr5": path_or_None, "pdfs": [paths], "zip_names": [...]}

    pB3.pdf มักเป็น แบบสรุปราคากลาง (ปร.5) จากการทดสอบกับ 3 โครงการ
    """
    result = {"pr5": None, "pdfs": [], "zip_names": []}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            log(f"  zip มี {len(names)} ไฟล์: {names}")
            result["zip_names"] = names

            for name in names:
                ext = Path(name).suffix.lower()
                if ext not in (".pdf", ".xlsx", ".xls"):
                    continue

                content = zf.read(name)
                safe_name = name.replace("/", "_").replace("\\", "_")
                dest = job_dir / safe_name
                dest.write_bytes(content)
                result["pdfs"].append(str(dest))
                log(f"    แตก: {safe_name} ({len(content):,} bytes)")

                # pB3 = ปร.5 (แบบสรุปราคากลาง) จากการทดสอบกับหลายโครงการ
                stem = Path(name).stem.lower()
                if stem == "pb3":
                    result["pr5"] = str(dest)
                    log(f"    → กำหนดเป็น ปร.5 (pr5)")

            # ถ้าไม่พบ pB3 ใช้ไฟล์ที่ 4 (index 3) แทน ถ้ามี
            if result["pr5"] is None and len(result["pdfs"]) >= 4:
                result["pr5"] = result["pdfs"][3]
                log(f"    → ใช้ไฟล์ที่ 4 เป็น pr5 (pB3 fallback)")

    except zipfile.BadZipFile as e:
        log(f"  zip error: {e}")

    return result


def fetch_tor_url(page, project_id: str, title: str = "") -> str:
    """
    สร้าง URL สำหรับค้นหา TOR บน e-GP
    e-GP process5 ไม่มี public API สำหรับ document listing
    → ใช้ search URL พร้อม keyword ชื่องาน เพื่อให้คลิกแล้วหาได้เร็วขึ้น
    """
    import urllib.parse
    keyword = title.strip() if title.strip() else project_id
    encoded = urllib.parse.quote(keyword)
    url = f"{PROCESS5_BASE}/egp-agpc01-web/announcement?keywordSearch={encoded}"
    log(f"  TOR URL: search link พร้อม keyword")
    return url


def download_job_documents(page, job: dict) -> dict:
    """
    ดาวน์โหลดเอกสาร BOQ zip ของงานหนึ่ง → แตก PDF
    คืนค่า {"status": ..., "pr5": path, "pdfs": [...]}
    """
    project_id = str(job.get("job_id", ""))
    # ตรวจสอบว่ามี folder ที่ rename แล้วหรือยัง
    existing = next(iter(DOWNLOAD_DIR.glob(f"*{project_id}*")), None)
    job_dir = existing if existing else DOWNLOAD_DIR / project_id
    job_dir.mkdir(parents=True, exist_ok=True)

    log(f"ดาวน์โหลด: {project_id} — {str(job.get('title', ''))[:60]}")

    # Step 0: ตรวจสอบว่างานถูกยกเลิกหรือไม่
    if check_cancelled(page, project_id):
        return {"status": "cancelled"}

    # Step 1: ดึง zipFileId
    zip_id = get_boq_zip_id(page, project_id)
    if not zip_id:
        return {"status": "no_boq"}

    # Step 2: ดาวน์โหลด zip
    zip_bytes = download_boq_zip(page, zip_id)
    if not zip_bytes:
        return {"status": "download_failed"}

    # Step 3: แตก PDF
    docs = extract_zip_pdfs(zip_bytes, job_dir)

    # Step 4: สร้าง TOR search URL พร้อม keyword ชื่องาน
    tor_url = fetch_tor_url(page, project_id, title=str(job.get("title", "")))

    meta = {
        "job_id": project_id,
        "downloaded_at": datetime.now().isoformat(),
        "zip_file_id": zip_id,
        "tor_url": tor_url,
        "files": docs,
    }
    (job_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    log(f"  เสร็จ: {len(docs['pdfs'])} ไฟล์ใน {job_dir.name}/")
    docs["status"] = "docs_downloaded"
    return docs


# ================================================================
# MAIN
# ================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sebastian Doc Downloader")
    parser.add_argument("--max", type=int, default=0, help="จำนวนงานสูงสุด (0=ทั้งหมด)")
    parser.add_argument("--job-id", help="ดาวน์โหลดเฉพาะ job_id นี้")
    args = parser.parse_args()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("Sebastian Doc Downloader — เริ่มต้น")
    log("=" * 60)

    log("อ่านงาน status='new' จาก Sheet 1...")
    jobs = read_new_jobs(max_jobs=args.max)
    if args.job_id:
        jobs = [j for j in jobs if str(j.get("job_id", "")) == args.job_id]
    log(f"พบ {len(jobs)} งานที่ต้องดาวน์โหลดเอกสาร")

    if not jobs:
        log("ไม่มีงานใหม่ — เสร็จสิ้น")
        return

    results = []

    with sync_playwright() as p:
        browser = connect_browser(p)
        page = new_page(browser)
        ensure_on_process5(page)

        for i, job in enumerate(jobs, 1):
            job_id = str(job.get("job_id", ""))
            log(f"\n[{i}/{len(jobs)}] {job_id}")

            try:
                docs = download_job_documents(page, job)
                status = docs.get("status", "docs_failed")
                results.append({"job_id": job_id, "status": status, "pr5": docs.get("pr5")})
                update_job_status(job_id, status)
                if docs.get("tor_url"):
                    update_tor_url(job_id, docs["tor_url"])
            except Exception as e:
                log(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                results.append({"job_id": job_id, "status": "docs_error"})
                update_job_status(job_id, "docs_error")

            time.sleep(1)

        page.close()

    success = sum(1 for r in results if r["status"] == "docs_downloaded")
    log(f"\nสรุป: {success}/{len(results)} งานดาวน์โหลดสำเร็จ")

    summary_path = Path(__file__).parent.parent / "data" / f"doc_download_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log(f"บันทึก summary: {summary_path}")


if __name__ == "__main__":
    main()
