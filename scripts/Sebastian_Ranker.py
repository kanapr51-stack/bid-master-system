"""
Sebastian_Ranker.py — จัดอันดับงานตามความน่าลงทุน → Sheet 4 (ranked_jobs)

เกณฑ์การให้คะแนน:
  - margin_pct (40%): margin สูง = ดี
  - budget (30%): งบสูง = โอกาสกำไรมาก
  - tor_confidence (20%): high/medium/low
  - data_completeness (10%): มี ปร.4, ปร.5, TOR ครบ
"""

import sys
import json
import glob
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET4_NAME    = "ranked_jobs"
DATA_DIR       = Path(__file__).parent.parent / "data"

HEADERS = [
    "rank", "job_id", "title", "department", "province", "publish_date",
    "budget", "total_cost", "margin_pct", "bid_price",
    "material_cost", "labor_cost", "machinery_cost",
    "W", "L", "T",
    "tor_confidence", "has_pr4", "has_pr5",
    "score", "recommendation", "status",
]

CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.3}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ================================================================
# SCORING
# ================================================================

def score_job(job: dict, all_budgets: list[float], all_margins: list[float]) -> float:
    """
    คำนวณ composite score 0–100
    """
    # 1. Margin score (40 points)
    margin = float(job.get("margin_pct", 0))
    if all_margins and max(all_margins) > min(all_margins):
        margin_norm = (margin - min(all_margins)) / (max(all_margins) - min(all_margins))
    else:
        margin_norm = 0.5
    margin_score = margin_norm * 40

    # 2. Budget score (30 points)
    budget = float(job.get("budget", 0))
    if all_budgets and max(all_budgets) > 0:
        budget_norm = min(budget / max(all_budgets), 1.0)
    else:
        budget_norm = 0
    budget_score = budget_norm * 30

    # 3. Confidence score (20 points)
    conf = str(job.get("tor_confidence", "low")).lower()
    confidence_score = CONFIDENCE_SCORE.get(conf, 0.3) * 20

    # 4. Data completeness (10 points)
    has_pr4 = job.get("has_pr4") in (True, "True", "Y", 1)
    has_pr5 = job.get("has_pr5") in (True, "True", "Y", 1)
    completeness = (int(has_pr4) + int(has_pr5)) / 2
    completeness_score = completeness * 10

    return round(margin_score + budget_score + confidence_score + completeness_score, 2)


def recommendation(job: dict) -> str:
    """สร้างคำแนะนำสั้นๆ"""
    margin = float(job.get("margin_pct", 0))
    conf = str(job.get("tor_confidence", "low")).lower()
    score = float(job.get("score", 0))

    if margin <= 0:
        return "ไม่แนะนำ — ต้นทุนเกินงบ"
    if margin < 5:
        return "ระวัง — margin ต่ำมาก"
    if score >= 70 and conf == "high":
        return "แนะนำสูง — margin ดี + ข้อมูลครบ"
    if score >= 50:
        return "แนะนำปานกลาง — ตรวจสอบเพิ่มเติม"
    return "ควรพิจารณา — ข้อมูลไม่สมบูรณ์"


# ================================================================
# SHEET OPERATIONS
# ================================================================

def get_sheet4():
    return open_sheet(SPREADSHEET_ID, SHEET4_NAME)


def ensure_headers(ws):
    first = ws.row_values(1)
    if not first or first[0] != "rank":
        ws.update([HEADERS], "A1")


def get_existing_ids(ws) -> set:
    return set(ws.col_values(2)[1:])   # column B = job_id


def job_to_row(rank: int, job: dict) -> list:
    return [
        rank,
        job.get("job_id", ""),
        job.get("title", ""),
        job.get("department", ""),
        job.get("province", ""),
        job.get("publish_date", ""),
        job.get("budget", ""),
        job.get("total_cost", ""),
        job.get("margin_pct", ""),
        job.get("bid_price", ""),
        job.get("material_cost", ""),
        job.get("labor_cost", ""),
        job.get("machinery_cost", ""),
        job.get("W", ""),
        job.get("L", ""),
        job.get("T", ""),
        job.get("tor_confidence", ""),
        "Y" if job.get("has_pr4") in (True, "True", "Y", 1) else "N",
        "Y" if job.get("has_pr5") in (True, "True", "Y", 1) else "N",
        job.get("score", ""),
        job.get("recommendation", ""),
        "ranked",
    ]


# ================================================================
# MAIN
# ================================================================

def rank_jobs(cost_results: list[dict]) -> list[dict]:
    """คำนวณ score และจัดอันดับ"""
    if not cost_results:
        return []

    all_budgets = [float(j.get("budget", 0)) for j in cost_results]
    all_margins = [float(j.get("margin_pct", 0)) for j in cost_results]

    for job in cost_results:
        job["score"] = score_job(job, all_budgets, all_margins)
        job["recommendation"] = recommendation(job)

    ranked = sorted(cost_results, key=lambda j: float(j.get("score", 0)), reverse=True)
    return ranked


def write_to_sheet4(ranked: list[dict]) -> int:
    """บันทึกอันดับลง Sheet 4"""
    if not ranked:
        return 0

    ws = get_sheet4()
    ensure_headers(ws)
    existing_ids = get_existing_ids(ws)

    new_rows = []
    rank = len(existing_ids) + 1

    for job in ranked:
        job_id = str(job.get("job_id", ""))
        if job_id in existing_ids:
            continue
        new_rows.append(job_to_row(rank, job))
        existing_ids.add(job_id)
        rank += 1

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        log(f"เพิ่ม {len(new_rows)} งานลง {SHEET4_NAME}")
    else:
        log("ไม่มีงานใหม่")

    return len(new_rows)


def load_latest_cost_results() -> list[dict]:
    """โหลด cost_results JSON ล่าสุด"""
    files = sorted(DATA_DIR.glob("cost_results_*.json"))
    if not files:
        return []
    latest = files[-1]
    log(f"โหลด: {latest.name}")
    return json.loads(latest.read_text(encoding="utf-8"))


def main():
    log("=" * 60)
    log("Sebastian Ranker — เริ่มต้น")
    log("=" * 60)

    cost_results = load_latest_cost_results()
    log(f"พบ {len(cost_results)} งานจาก cost results")

    if not cost_results:
        log("ไม่มีข้อมูลต้นทุน — เสร็จสิ้น")
        return

    ranked = rank_jobs(cost_results)

    # แสดง preview
    log("\nอันดับ (preview 5 อันดับแรก):")
    for i, job in enumerate(ranked[:5], 1):
        log(f"  #{i} score={job['score']:.1f} margin={job['margin_pct']:.1f}% — {job['title'][:50]}")

    added = write_to_sheet4(ranked)

    # บันทึก ranked JSON
    out_path = DATA_DIR / f"ranked_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    out_path.write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log(f"\nสรุป: rank {len(ranked)} งาน, เพิ่ม Sheet 4: {added} งาน")
    log(f"บันทึก: {out_path}")


if __name__ == "__main__":
    main()
