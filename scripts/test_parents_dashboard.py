"""test_parents_dashboard.py — standalone assert runner (ไม่มี pytest).
รัน: python scripts/test_parents_dashboard.py → exit 0 ถ้าผ่าน, 1 ถ้า fail
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from build_parents_dashboard import compute_data, render_html  # noqa: E402

DB = str(Path(__file__).parent.parent / "data" / "winner_history.db")


def main():
    d = compute_data(DB)
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append(msg)

    # hero
    chk(d["total_jobs"] == 52525, f"total_jobs={d['total_jobs']} != 52525")
    chk(45000 <= d["total_value_m"] <= 47000, f"total_value_m={d['total_value_m']}")
    chk(d["year_min"] == "2558" and d["year_max"] == "2568", f"years {d['year_min']}-{d['year_max']}")

    # market — รวม %share ≈ 100, ถนน อันดับ 1 และ > 50%
    cats = d["market"]
    chk(abs(sum(c["pct"] for c in cats) - 100) < 1.0, "market pct sum != 100")
    top = max(cats, key=lambda c: c["value_m"])
    chk(top["cat"] == "ถนน" and top["pct"] > 50, f"top cat {top['cat']} {top['pct']}%")

    # our rank — ราง/ท่อ rank 11
    rank = {r["cat"]: r["rank"] for r in d["our_rank"] if r["rank"]}
    chk(rank.get("รางระบายน้ำ/ท่อ") == 11, f"ราง rank={rank.get('รางระบายน้ำ/ท่อ')} != 11")

    # trend — ไฟฟ้า โต, แหล่งน้ำ หด
    tr = {t["cat"]: t["pct_v"] for t in d["trend"]}
    chk(tr.get("ไฟฟ้า/ส่องสว่าง", 0) > 100, f"ไฟฟ้า trend={tr.get('ไฟฟ้า/ส่องสว่าง')}")
    chk(tr.get("แหล่งน้ำ/ชลประทาน", 0) < 0, f"แหล่งน้ำ trend={tr.get('แหล่งน้ำ/ชลประทาน')}")

    # opportunity = core เทรนด์สูงสุด ที่เราไม่เล่น → ไฟฟ้า
    chk(d["opportunity"]["cat"] == "ไฟฟ้า/ส่องสว่าง", f"opportunity={d['opportunity']['cat']}")

    # รายละเอียดเพิ่ม: competitors / area / our_jobs / year_series
    chk(len(d["competitors"]) == 7, f"competitors cats={len(d['competitors'])}")
    chk(len(d["competitors"]["ราง/ท่อ"]) >= 5, "competitors ราง/ท่อ < 5")
    chk(any(w["ours"] for w in d["competitors"]["ราง/ท่อ"]), "เราไม่อยู่ใน top คู่แข่งราง")
    provs = {p["prov"] for p in d["area_prov"]}
    chk("นครพนม" in provs and "บึงกาฬ" in provs, f"area_prov={provs}")
    chk(len(d["area_tambon"]) == 15, f"area_tambon={len(d['area_tambon'])}")
    chk(250 <= len(d["our_jobs"]) <= 320, f"our_jobs={len(d['our_jobs'])}")
    chk(d["our_total_m"] > 100, f"our_total_m={d['our_total_m']}")
    chk(len(d["year_series"]["years"]) == 11 and len(d["year_series"]["series"]) == 7, "year_series shape")

    # render HTML
    html = render_html(d)
    chk("สรุปผลการวิเคราะห์ตลาดงานก่อสร้าง" in html, "ไม่มีหัวเว็บ")
    chk("จัดทำโดยน้องกัญจน์" in html, "ไม่มีเครดิตน้องกัญจน์")
    chk('name="robots" content="noindex' in html, "ไม่มี noindex")
    chk("chart.umd" in html.lower() or "chart.js" in html.lower(), "ไม่มี Chart.js")
    chk("#C62828" in html or "#c62828" in html.lower(), "ไม่มีสีแดงธีม")
    chk("46,063" in html or "46063" in html.replace(",", ""), "ไม่มีตัวเลขตลาดรวม")
    chk("ไฟฟ้า" in html, "ไม่มีหมวดไฟฟ้า")
    chk("คู่แข่งแต่ละหมวด" in html, "ไม่มี section คู่แข่ง")
    chk("งานอยู่พื้นที่ไหน" in html, "ไม่มี section พื้นที่")
    chk("ผลงานบริษัทเรา" in html, "ไม่มี section ผลงานเรา")
    chk("เทรนด์รายปี" in html, "ไม่มี section กราฟรายปี")
    chk(len(html) > 20000, f"HTML สั้นผิดปกติ ({len(html)} ตัว)")

    if fails:
        print("❌ FAIL:\n" + "\n".join("  " + f for f in fails))
        sys.exit(1)
    print(f"✅ PASS — total {d['total_value_m']:,.0f} ลบ., opportunity={d['opportunity']['label']}, html={len(html):,} ตัว")


if __name__ == "__main__":
    main()
