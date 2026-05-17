"""
filter_target_deptids.py — กลั่นกรอง deptId catalog → target depts สำหรับ Phase 1

Strategy (2 ชั้น):
  A) Title keyword match — title มีคำว่า นครพนม/บึงกาฬ/บ้านแพง/บึงโขงหลง
  B) Reverse projectId lookup — ถ้า all_jobs มี projectId ของพื้นที่เป้าหมาย และ
     เจอใน catalog → deptId นั้นน่าจะเกี่ยวข้อง

Output:
  data/target_deptids.json — list ของ deptId ที่จะ poll
  data/target_deptids_report.md — สรุปเหตุผลแต่ละ dept
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_FILE = DATA_DIR / "egp_deptid_catalog.json"
OUT_FILE = DATA_DIR / "target_deptids.json"
REPORT_FILE = DATA_DIR / "target_deptids_report.md"

TARGET_KEYWORDS = {
    "province": ["นครพนม", "บึงกาฬ"],
    "district": ["บ้านแพง", "บึงโขงหลง"],
    "adjacent_province": ["หนองคาย", "สกลนคร", "มุกดาหาร"],
}

# Construction-related title keywords — national depts ที่อาจทำในจังหวัดเป้าหมาย
CONSTRUCTION_KEYWORDS = ["ก่อสร้าง", "ทาง", "ถนน", "สะพาน", "อาคาร", "ปรับปรุง", "ซ่อม"]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def keyword_filter(catalog: dict) -> dict[str, dict]:
    """Filter deptIds whose titles mention target keywords.
    Returns: { dept_id: {reasons: [...], matched_titles: [...]} }
    """
    matched: dict[str, dict] = {}
    all_target_kws = (
        TARGET_KEYWORDS["province"]
        + TARGET_KEYWORDS["district"]
    )
    adjacent = TARGET_KEYWORDS["adjacent_province"]

    for dept_id, info in catalog.items():
        reasons = []
        matched_titles = []
        for title in info.get("titles", []):
            for kw in all_target_kws:
                if kw in title:
                    reasons.append(f"title↪{kw}")
                    matched_titles.append(title[:100])
                    break
            else:
                for kw in adjacent:
                    if kw in title:
                        reasons.append(f"title↪{kw}(nearby)")
                        matched_titles.append(title[:100])
                        break
        if reasons:
            matched[dept_id] = {
                "reasons": list(dict.fromkeys(reasons)),  # unique, ordered
                "matched_titles": matched_titles[:5],
                "item_count": info.get("item_count", 0),
            }
    return matched


def try_sheet_reverse_lookup(catalog: dict) -> dict[str, dict]:
    """ถ้า sheets_client เข้าถึงได้ → ลอง reverse lookup
    หา projectIds ของ all_jobs ที่ province ตรงเป้า → map ไป deptId ใน catalog
    """
    try:
        from sheets_client import open_sheet
    except Exception as e:
        log(f"⚠️ sheets_client import fail ({e}) — skip reverse lookup")
        return {}

    try:
        SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
        ws = open_sheet(SPREADSHEET_ID, "all_jobs")
        rows = ws.get_all_values()
        if len(rows) < 2:
            return {}
        headers = rows[0]
        h_idx = {h: i for i, h in enumerate(headers)}
        jid_col = h_idx.get("job_id", 0)
        prov_col = h_idx.get("province", -1)
        district_col = h_idx.get("district", -1)

        target_jids: set[str] = set()
        for r in rows[1:]:
            if jid_col >= len(r):
                continue
            prov = r[prov_col].strip() if 0 <= prov_col < len(r) else ""
            dist = r[district_col].strip() if 0 <= district_col < len(r) else ""
            if any(kw in prov for kw in TARGET_KEYWORDS["province"]) or any(
                kw in dist for kw in TARGET_KEYWORDS["district"]
            ):
                target_jids.add(r[jid_col].strip())

        log(f"  Sheet: {len(target_jids)} target projectIds in all_jobs")

        # Reverse lookup
        result: dict[str, dict] = {}
        for dept_id, info in catalog.items():
            pids = set(info.get("projectIds", []))
            matched = pids & target_jids
            if matched:
                result[dept_id] = {
                    "reasons": [f"projectId↪{len(matched)}match"],
                    "matched_project_ids": list(matched)[:10],
                    "item_count": info.get("item_count", 0),
                }
        return result
    except Exception as e:
        log(f"⚠️ Sheet reverse lookup failed: {e}")
        return {}


def merge_results(a: dict, b: dict) -> dict:
    """รวม 2 sources of dept matches"""
    out: dict = {}
    for d, info in a.items():
        out[d] = {"sources": ["keyword"], **info}
    for d, info in b.items():
        if d in out:
            out[d]["sources"].append("reverse_pid")
            out[d]["reasons"].extend(info.get("reasons", []))
            if "matched_project_ids" in info:
                out[d]["matched_project_ids"] = info["matched_project_ids"]
        else:
            out[d] = {"sources": ["reverse_pid"], **info}
    return out


def main():
    if not CATALOG_FILE.exists():
        log(f"❌ ไม่พบ {CATALOG_FILE} — รัน scan_egp_deptids.py ก่อน")
        sys.exit(1)

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    log(f"Catalog: {len(catalog)} active depts")

    keyword_matches = keyword_filter(catalog)
    log(f"Keyword filter: {len(keyword_matches)} matches")

    reverse_matches = try_sheet_reverse_lookup(catalog)
    log(f"Reverse lookup: {len(reverse_matches)} matches")

    merged = merge_results(keyword_matches, reverse_matches)
    log(f"Total target depts: {len(merged)}")

    target_list = sorted(merged.keys())
    OUT_FILE.write_text(
        json.dumps(target_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Report
    lines = [
        f"# Target DeptIds Report ({datetime.now().isoformat(timespec='seconds')})",
        "",
        f"- Catalog size: **{len(catalog)}** active depts",
        f"- Keyword match: **{len(keyword_matches)}**",
        f"- Reverse projectId match: **{len(reverse_matches)}**",
        f"- **Total target**: **{len(merged)}**",
        "",
        "## Target Depts",
        "",
        "| DeptId | Items | Sources | Reasons |",
        "|---|---|---|---|",
    ]
    for d in target_list:
        info = merged[d]
        sources = ",".join(info.get("sources", []))
        reasons = "; ".join(info.get("reasons", [])[:3])
        lines.append(f"| {d} | {info.get('item_count', 0)} | {sources} | {reasons} |")

    if any("matched_titles" in v for v in merged.values()):
        lines.append("")
        lines.append("## Sample Matched Titles")
        for d in target_list:
            titles = merged[d].get("matched_titles", [])
            if titles:
                lines.append(f"\n### {d}")
                for t in titles[:3]:
                    lines.append(f"- {t}")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")

    log(f"✅ Target list: {OUT_FILE}")
    log(f"✅ Report: {REPORT_FILE}")
    log(f"   {target_list}")


if __name__ == "__main__":
    main()
