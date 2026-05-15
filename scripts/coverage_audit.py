"""
coverage_audit.py — วัดขนาดบ่อ (pond size) เทียบกับปลาที่จับได้

วัด 3 ชั้น:
  1. API Total   — eGP มีงาน e-bidding ในพื้นที่กี่งาน (totalRecords จาก API)
  2. Keyword Gap — หน่วยงานในพื้นที่ที่ไม่อยู่ใน DEPT_PROVINCE_MAP
  3. Filter Drop — งานที่ Classifier/Scraper ตัดทิ้งในแต่ละขั้น

วิธีใช้:
    1. เปิด Chrome: Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
    2. python coverage_audit.py

ผลลัพธ์จะแสดงใน terminal + บันทึกลง data/coverage_report.json
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, date
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from Sebastian_Scraper import DEPT_PROVINCE_MAP, connect_browser, SEARCH_URL_PROCESS5

DEBUG_PORT     = 9222
SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
REPORT_FILE    = Path(__file__).parent.parent / "data" / "coverage_report.json"
TARGET_PROVINCES = ["นครพนม", "บึงกาฬ"]

# eGP methodId=16 → e-bidding เท่านั้น
METHOD_EBIDDING = "16"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ================================================================
# ชั้น 1: API Total — ค้นจังหวัดโดยตรงบน eGP
# ================================================================

def fetch_province_total(page, province: str) -> dict:
    """
    ค้นหาใน eGP ด้วย keyword=จังหวัด (ไม่กรอง construction)
    → ดึง totalRecords จาก API response (ขนาดบ่อจริง)
    คืนค่า: {
        "keyword": province,
        "egp_total_all_methods":   N,   # ทุกวิธีจัดซื้อ
        "egp_total_ebidding":      N,   # e-bidding เท่านั้น
        "first_page_items":        N,
    }
    """
    log(f"\n[Layer 1] ค้น eGP: '{province}'")
    result = {"keyword": province, "egp_total_all_methods": None, "egp_total_ebidding": None}

    # ── รอ search input ──
    search_input = None
    for sel in ["input[name*='keyword']", "input[placeholder*='ค้นหา']", "input[type='search']"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                search_input = el
                break
        except Exception:
            pass
    if not search_input:
        log("  ไม่พบ search input")
        return result

    # ── type keyword ──
    search_input.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    time.sleep(0.3)
    page.keyboard.type(province, delay=50)
    time.sleep(0.8)

    # ── ค้นหา (ทุก method ก่อน) ──
    captured = {}

    def capture(resp):
        url = resp.url
        if ("egp-atpj27-service" in url and "announcement" in url
                and "sumProject" not in url and "cfturnstile" not in url):
            try:
                body = resp.json()
                data = body.get("data", {})
                total = data.get("totalRecords") or data.get("totalCount") or data.get("total")
                items = data.get("data", [])
                captured["all"] = {
                    "total":       total,
                    "first_items": len(items),
                    "raw_keys":    list(data.keys()),
                }
            except Exception:
                pass

    page.on("response", capture)

    try:
        with page.expect_response(
            lambda r: (
                "egp-atpj27-service" in r.url
                and "announcement" in r.url
                and "sumProject" not in r.url
            ),
            timeout=25000,
        ):
            try:
                page.locator("button:has-text('ค้นหา')").first.click(timeout=8000)
            except Exception:
                search_input.press("Enter")
        time.sleep(2)
    except Exception as e:
        log(f"  search error: {e}")

    page.remove_listener("response", capture)

    if "all" in captured:
        result["egp_total_all_methods"] = captured["all"]["total"]
        result["first_page_items"]      = captured["all"]["first_items"]
        result["api_data_keys"]         = captured["all"]["raw_keys"]
        log(f"  totalRecords (all methods): {captured['all']['total']}")
        log(f"  API data keys: {captured['all']['raw_keys']}")
    else:
        log("  ไม่สามารถดัก API response ได้")

    # ── ตอนนี้กรอง method=e-bidding แล้วค้นใหม่ ──
    # ลอง intercept call ที่มี methodId=16 จากการ filter UI
    # (ถ้า UI ไม่มี filter เราจะใช้ API โดยตรง)
    time.sleep(1)
    e_captured = {}

    def capture_ebid(resp):
        url = resp.url
        if ("egp-atpj27-service" in url and "announcement" in url
                and "sumProject" not in url
                and ("methodId=16" in url or "method_id=16" in url)):
            try:
                body = resp.json()
                data = body.get("data", {})
                total = data.get("totalRecords") or data.get("totalCount") or data.get("total")
                e_captured["ebid"] = {"total": total}
            except Exception:
                pass

    page.on("response", capture_ebid)

    # ลอง direct API call: ต่อ URL base + methodId=16
    # (ใช้ fetch ผ่าน JS เพราะมี session cookie อยู่แล้ว)
    direct_js = """async (province) => {
        const base = 'https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement';
        const params = new URLSearchParams({
            keyword: province,
            methodId: '16',
            page: '1',
            size: '10',
        });
        try {
            const r = await fetch(`${base}?${params}`, {credentials: 'include'});
            const body = await r.json();
            const data = body && body.data ? body.data : {};
            return {
                total: data.totalRecords || data.totalCount || data.total || null,
                first_items: (data.data || []).length,
                keys: Object.keys(data),
            };
        } catch(e) { return {error: e.toString()}; }
    }"""

    try:
        ebid_data = page.evaluate(direct_js, province)
        if ebid_data and not ebid_data.get("error"):
            result["egp_total_ebidding"] = ebid_data.get("total")
            result.setdefault("first_page_items", ebid_data.get("first_items"))
            if not result.get("api_data_keys"):
                result["api_data_keys"] = ebid_data.get("keys", [])
            log(f"  totalRecords (e-bidding): {ebid_data.get('total')} | keys: {ebid_data.get('keys')}")
        else:
            log(f"  direct API error: {ebid_data}")
    except Exception as e:
        log(f"  direct API exception: {e}")

    page.remove_listener("response", capture_ebid)
    return result


# ================================================================
# ชั้น 2: Keyword Gap — หน่วยงานในพื้นที่ที่เราไม่ได้ cover
# ================================================================

def fetch_unique_departments(page, province: str, max_pages: int = 20) -> set:
    """
    ดึง department ทั้งหมดที่โพสต์งาน e-bidding ใน province นี้บน eGP
    คืน set ของชื่อ department (unique)
    """
    log(f"\n[Layer 2] ดึง unique departments: '{province}' (e-bidding)")

    js_fetch = """async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const body = await r.json();
            const data = body && body.data ? body.data : {};
            return {
                items: (data.data || []).map(i => i.deptSubName || i.announceSubDesc || ''),
                total: data.totalRecords || data.totalCount || data.total || 0,
            };
        } catch(e) { return {error: e.toString()}; }
    }"""

    base = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
    depts = set()
    total = None

    for p_num in range(1, max_pages + 1):
        from urllib.parse import urlencode
        params = urlencode({"keyword": province, "methodId": "16", "page": str(p_num), "size": "20"})
        url = f"{base}?{params}"

        try:
            res = page.evaluate(js_fetch, url)
            if res.get("error"):
                log(f"  page {p_num} error: {res['error']}")
                break
            items = res.get("items", [])
            if total is None:
                total = res.get("total")
                log(f"  eGP total e-bidding for '{province}': {total}")
            if not items:
                log(f"  page {p_num}: 0 items — หยุด")
                break
            for d in items:
                d = (d or "").strip()
                if d:
                    depts.add(d)
            log(f"  page {p_num}: {len(items)} items, unique depts so far: {len(depts)}")
            time.sleep(0.5)
        except Exception as e:
            log(f"  page {p_num} exception: {e}")
            break

    return depts, total


def analyze_keyword_gap(dept_set: set, province_filter: str) -> dict:
    """
    เปรียบเทียบ dept_set จาก eGP กับ DEPT_PROVINCE_MAP
    คืน: depts ที่อยู่ในพื้นที่แต่เราไม่ได้ search
    """
    our_keywords = {
        k for k, v in DEPT_PROVINCE_MAP.items() if v == province_filter
    }

    covered = set()
    not_covered = set()

    for dept in dept_set:
        dept_lower = dept.lower()
        matched = False
        for kw in our_keywords:
            if kw in dept:
                matched = True
                break
        if matched:
            covered.add(dept)
        else:
            not_covered.add(dept)

    return {
        "total_unique_depts_on_egp": len(dept_set),
        "covered_by_our_keywords":   len(covered),
        "not_covered":               sorted(not_covered),
        "coverage_dept_pct":         round(len(covered) / len(dept_set) * 100, 1) if dept_set else 0,
    }


# ================================================================
# ชั้น 3: Filter Drop — อ่าน all_jobs แล้วจำลอง Classifier
# ================================================================

def analyze_our_pipeline() -> dict:
    """อ่าน all_jobs แล้ว count ตาม filter steps"""
    log("\n[Layer 3] วิเคราะห์ pipeline filter drops...")

    sys.path.insert(0, str(Path(__file__).parent))
    from Sebastian_Classifier import (
        is_in_target_province, is_construction_job, ALL_JOBS_HEADERS, parse_thai_date
    )

    ws = open_sheet(SPREADSHEET_ID, "all_jobs")
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return {"error": "all_jobs ว่าง"}

    headers = all_values[0]
    h_idx = {h: i for i, h in enumerate(headers)}

    def g(row, key):
        i = h_idx.get(key, -1)
        return row[i] if 0 <= i < len(row) else ""

    today = date.today()
    stats = {
        "total_in_all_jobs": 0,
        "no_job_id":         0,
        "non_ebidding":      0,
        "off_province":      0,
        "non_construction":  0,
        "passed_filters":    0,
        "active":            0,
        "pending":           0,
        "has_winner":        0,
        "no_deadline":       0,
        "province_breakdown": {},
        "construction_filter_examples": [],  # sample ที่ถูกตัด
    }

    sample_dropped = []

    for r in all_values[1:]:
        stats["total_in_all_jobs"] += 1
        jid = g(r, "job_id")
        if not jid:
            stats["no_job_id"] += 1
            continue
        if g(r, "procurement_type") != "e-bidding":
            stats["non_ebidding"] += 1
            continue

        row_dict = {h: g(r, h) for h in ALL_JOBS_HEADERS if h in h_idx}

        if not is_in_target_province(row_dict):
            stats["off_province"] += 1
            continue

        # นับ province breakdown (สำหรับงานที่ผ่าน province filter)
        prov = g(r, "province") or "unknown"
        stats["province_breakdown"][prov] = stats["province_breakdown"].get(prov, 0) + 1

        title = g(r, "title")
        if not is_construction_job(title):
            stats["non_construction"] += 1
            if len(sample_dropped) < 10:
                sample_dropped.append(title[:80])
            continue

        stats["passed_filters"] += 1

        dl = parse_thai_date(g(r, "deadline"))
        if dl is None:
            stats["no_deadline"] += 1
        elif dl >= today:
            stats["active"] += 1
        else:
            stats["pending"] += 1

    stats["construction_filter_examples"] = sample_dropped
    log(f"  all_jobs: {stats['total_in_all_jobs']} rows")
    log(f"  passed province+construction: {stats['passed_filters']}")
    log(f"  → active: {stats['active']} | pending: {stats['pending']} | no_deadline: {stats['no_deadline']}")
    return stats


# ================================================================
# MAIN
# ================================================================

def main():
    log("=" * 60)
    log("Coverage Audit — วัดขนาดบ่อ vs ปลาที่จับได้")
    log("=" * 60)

    report = {
        "generated_at": datetime.now().isoformat(),
        "layers": {}
    }

    # ── Layer 3: Pipeline (ไม่ต้อง Chrome) ──
    pipeline_stats = analyze_our_pipeline()
    report["layers"]["3_pipeline_filter_drops"] = pipeline_stats

    # ── Layer 1 + 2: ต้องใช้ Chrome ──
    log("\nเชื่อมต่อ Chrome...")
    with sync_playwright() as p:
        try:
            browser = connect_browser(p)
        except RuntimeError as e:
            log(f"  ⚠️ {e}")
            log("  ข้าม Layer 1 + 2 (ต้องเปิด Chrome ก่อน)")
            _print_report(report)
            return

        page = browser.contexts[0].new_page()

        log("โหลด process5...")
        try:
            page.goto(SEARCH_URL_PROCESS5, wait_until="load", timeout=45000)
            time.sleep(6)
            page.wait_for_selector("input[name*='keyword']", timeout=20000)
        except Exception as e:
            log(f"  ⚠️ โหลดหน้าไม่ได้: {e}")
            _print_report(report)
            return

        layer1 = {}
        layer2 = {}

        for prov in TARGET_PROVINCES:
            # Layer 1: total count
            l1 = fetch_province_total(page, prov)
            layer1[prov] = l1
            time.sleep(2)

            # Layer 2: unique departments (max 15 pages = 300 items)
            depts, egp_total = fetch_unique_departments(page, prov, max_pages=15)
            gap = analyze_keyword_gap(depts, prov)
            gap["egp_total_ebidding_confirmed"] = egp_total
            layer2[prov] = gap

            log(f"\n  [{prov}] Dept coverage: {gap['coverage_dept_pct']}%")
            log(f"  [{prov}] ไม่ cover {len(gap['not_covered'])} departments:")
            for d in gap["not_covered"][:20]:
                log(f"    ❌ {d}")

            time.sleep(3)

        page.close()

    report["layers"]["1_api_totals"] = layer1
    report["layers"]["2_keyword_gap"] = layer2

    _print_report(report)

    # บันทึก
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nรายงานบันทึกที่: {REPORT_FILE}")


def _print_report(report: dict):
    log("\n" + "=" * 60)
    log("สรุปผล Coverage Audit")
    log("=" * 60)

    l3 = report["layers"].get("3_pipeline_filter_drops", {})
    if l3 and not l3.get("error"):
        log(f"\n[Layer 3] Pipeline filter drops:")
        log(f"  all_jobs ทั้งหมด:           {l3.get('total_in_all_jobs', 0):,}")
        log(f"  ไม่ใช่ e-bidding:           {l3.get('non_ebidding', 0):,}")
        log(f"  นอกพื้นที่:                  {l3.get('off_province', 0):,}")
        log(f"  ไม่ใช่งานก่อสร้าง:           {l3.get('non_construction', 0):,}")
        log(f"  ผ่านฟิลเตอร์ทั้งหมด:        {l3.get('passed_filters', 0):,}")
        log(f"  → active_bidding:           {l3.get('active', 0):,}")
        log(f"  → pending_award:            {l3.get('pending', 0):,}")
        log(f"  → ไม่มี deadline:            {l3.get('no_deadline', 0):,}")
        log(f"\n  Province breakdown (passed province filter):")
        for prov, cnt in sorted(l3.get("province_breakdown", {}).items(), key=lambda x: -x[1]):
            log(f"    {prov}: {cnt:,}")
        dropped = l3.get("construction_filter_examples", [])
        if dropped:
            log(f"\n  ตัวอย่างงานที่ถูกตัดทิ้ง (non_construction sample):")
            for ex in dropped:
                log(f"    ✂️  {ex}")

    l1 = report["layers"].get("1_api_totals", {})
    l2 = report["layers"].get("2_keyword_gap", {})

    if l1 or l2:
        log(f"\n[Layer 1+2] ขนาดบ่อ vs ปลาที่จับได้:")
        for prov in TARGET_PROVINCES:
            api = l1.get(prov, {})
            gap = l2.get(prov, {})
            egp_total = api.get("egp_total_ebidding") or gap.get("egp_total_ebidding_confirmed")
            our_total = l3.get("province_breakdown", {}).get(prov, 0) if l3 else "?"

            log(f"\n  จังหวัด: {prov}")
            log(f"    eGP มีงาน e-bidding:    {egp_total or '?'}")
            log(f"    เราดึงมาได้ (ก่อน construction filter): {our_total}")
            if egp_total and isinstance(our_total, int) and egp_total > 0:
                log(f"    Province recall:       {our_total / egp_total * 100:.1f}%")
            log(f"    Dept coverage:         {gap.get('coverage_dept_pct', '?')}%")
            not_cov = gap.get("not_covered", [])
            if not_cov:
                log(f"    ❌ Departments ที่ไม่ได้ cover ({len(not_cov)} แห่ง):")
                for d in not_cov[:10]:
                    log(f"       {d}")
                if len(not_cov) > 10:
                    log(f"       ... และอีก {len(not_cov) - 10} แห่ง (ดูใน {REPORT_FILE.name})")


if __name__ == "__main__":
    main()
