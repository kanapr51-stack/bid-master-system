"""build_parents_dashboard.py — สร้างหน้าเว็บ static สรุปวิเคราะห์ตลาดงานก่อสร้าง (พ่อแม่).
อ่าน winner_history.db (column work_type, primary) → คำนวณ size/share/trend → เขียน
dashboard/parents/index.html (self-contained). ดู spec 2026-06-05-parents-dashboard-design.md.
รัน: python scripts/build_parents_dashboard.py
"""
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

OUR = ("บ้านแพงทรัพย์คอนกรีต", "ยศประทานรุ่งเรืองทรัพย์")
CORE = ["ถนน", "รางระบายน้ำ/ท่อ", "แหล่งน้ำ/ชลประทาน", "อาคาร", "สะพาน", "ไฟฟ้า/ส่องสว่าง", "ดิน/ปรับพื้นที่"]
ORDER = CORE + ["OTHER", "UNKNOWN"]
EARLY = ["2561", "2562"]
RECENT = ["2567", "2568"]
LABEL = {"รางระบายน้ำ/ท่อ": "ราง/ท่อ", "แหล่งน้ำ/ชลประทาน": "แหล่งน้ำ", "ดิน/ปรับพื้นที่": "ดิน"}


def short(cat):
    return LABEL.get(cat, cat)


def is_ours(w):
    return any(o in (w or "") for o in OUR)


def compute_data(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT work_type, fiscal_year, win_price, winner "
        "FROM winner_history WHERE work_type IS NOT NULL"
    ).fetchall()
    c.close()

    cat_n, cat_v = defaultdict(int), defaultdict(float)
    cat_win = defaultdict(lambda: defaultdict(float))   # cat -> winner(merged) -> value
    yc_v = defaultdict(lambda: defaultdict(float))       # year -> cat -> value
    years = set()
    for wt, fy, wp, winner in rows:
        wp = wp or 0
        cat_n[wt] += 1
        cat_v[wt] += wp
        key = "★เรา" if is_ours(winner) else (winner or "(ไม่ระบุ)")
        cat_win[wt][key] += wp
        if fy:
            yc_v[fy][wt] += wp
            years.add(fy)

    total_v = sum(cat_v.values())
    total_n = sum(cat_n.values())
    ordered = [k for k in ORDER if k in cat_v]

    market = [{
        "cat": cat, "label": short(cat), "jobs": cat_n[cat],
        "value_m": round(cat_v[cat] / 1e6, 1),
        "pct": round(cat_v[cat] / total_v * 100, 1),
        "avg_m": round(cat_v[cat] / cat_n[cat] / 1e6, 2) if cat_n[cat] else 0,
    } for cat in ordered]

    our_rank = []
    for cat in CORE:
        wins = cat_win[cat]
        cat_total = sum(wins.values())
        ranked = sorted(wins.items(), key=lambda x: -x[1])
        our_val = wins.get("★เรา", 0)
        rk = next((i for i, (w, _) in enumerate(ranked, 1) if w == "★เรา"), None)
        leader = ranked[0] if ranked else ("-", 0)
        our_rank.append({
            "cat": cat, "label": short(cat),
            "our_value_m": round(our_val / 1e6, 1),
            "share": round(our_val / cat_total * 100, 2) if cat_total else 0,
            "rank": rk, "players": len(wins),
            "leader": "เรา" if leader[0] == "★เรา" else leader[0][:36],
            "leader_share": round(leader[1] / cat_total * 100, 1) if cat_total else 0,
        })

    def avg_v(cat, ys):
        return sum(yc_v[y].get(cat, 0) for y in ys) / len(ys)

    trend = []
    for cat in CORE:
        ev, rv = avg_v(cat, EARLY), avg_v(cat, RECENT)
        pct = round((rv - ev) / ev * 100, 1) if ev > 0 else None
        trend.append({"cat": cat, "label": short(cat),
                      "early_m": round(ev / 1e6, 1), "recent_m": round(rv / 1e6, 1), "pct_v": pct})

    # opportunity = หมวดที่เราไม่เล่น (our value=0) + กำลังโต (pct>0) → เลือก "ตลาดปัจจุบันใหญ่สุด"
    # (ใช้ recent_m ไม่ใช่ %สูงสุด — กัน %พุ่งจากฐานจิ๋วหลอกตา เช่น ดิน +779% แต่ตลาดเล็ก)
    our_zero = {r["cat"] for r in our_rank if r["our_value_m"] == 0}
    cands = [t for t in trend if t["cat"] in our_zero and t["pct_v"] is not None and t["pct_v"] > 0]
    opp = max(cands, key=lambda t: t["recent_m"]) if cands else max(trend, key=lambda t: t["recent_m"])

    now = datetime.now()
    return {
        "total_value_m": round(total_v / 1e6, 0),
        "total_jobs": total_n,
        "year_min": min(years), "year_max": max(years),
        "market": market, "our_rank": our_rank, "trend": trend,
        "opportunity": opp,
        "build_date": f"{now.day}/{now.month}/{now.year + 543}",
    }


_TITLE = "สรุปผลการวิเคราะห์ตลาดงานก่อสร้าง นครพนม-บึงกาฬ"


def render_html(d):
    data_json = json.dumps(d, ensure_ascii=False)
    title_full = f"{_TITLE} ตั้งแต่ปี พ.ศ. {d['year_min']}-{d['year_max']} จัดทำโดยน้องกัญจน์"
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{_TITLE}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{{--red:#C62828;--red2:#E53935;--ink:#222;--bg:#fff;--muted:#777;--line:#eee;}}
*{{box-sizing:border-box;}}
body{{margin:0;font-family:'Sarabun',sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;}}
.wrap{{max-width:560px;margin:0 auto;padding:16px;}}
header{{text-align:center;padding:20px 8px;border-bottom:3px solid var(--red);}}
header h1{{font-size:19px;margin:0 0 12px;color:var(--red);font-weight:700;}}
.big{{font-size:40px;font-weight:700;color:var(--red);line-height:1.1;}}
.big small{{display:block;font-size:14px;color:var(--muted);font-weight:400;margin-top:4px;}}
section{{padding:22px 4px;border-bottom:1px solid var(--line);}}
h2{{font-size:17px;margin:0 0 14px;}}
.card{{background:#fafafa;border-radius:12px;padding:14px;margin:8px 0;border-left:4px solid var(--red);}}
.card .medal{{font-size:15px;font-weight:700;}}
.rankrow{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);}}
.rankrow:last-child{{border:0;}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px;}}
th,td{{text-align:right;padding:7px 6px;border-bottom:1px solid var(--line);}}
th:first-child,td:first-child{{text-align:left;}}
th{{background:var(--red);color:#fff;font-weight:600;}}
details{{margin-top:10px;}}
summary{{color:var(--red);font-weight:600;cursor:pointer;padding:8px 0;list-style:none;}}
summary::after{{content:" \\25B8";}}
details[open] summary::after{{content:" \\25BE";}}
.opp{{background:linear-gradient(135deg,var(--red),var(--red2));color:#fff;border-radius:14px;padding:20px;text-align:center;}}
.opp .n{{font-size:30px;font-weight:700;margin:6px 0;}}
.up{{color:#2e7d32;font-weight:700;}}.down{{color:var(--red);font-weight:700;}}.flat{{color:var(--muted);}}
footer{{text-align:center;color:var(--muted);font-size:12px;padding:20px;}}
canvas{{max-width:100%;}}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>{title_full}</h1>
<div class="big">{d['total_value_m']:,.0f}<small>มูลค่าตลาดรวม (ล้านบาท) &middot; {d['total_jobs']:,} งาน</small></div>
</header>

<section>
<h2>1&#65039;&#8419; ตลาดใหญ่แค่ไหน — แยกตามหมวดงาน</h2>
<canvas id="mkt" height="220"></canvas>
<details><summary>ดูตารางเต็ม</summary>
<table><thead><tr><th>หมวด</th><th>มูลค่า (ลบ.)</th><th>%</th><th>เฉลี่ย/งาน</th></tr></thead>
<tbody id="mkt-tb"></tbody></table></details>
</section>

<section>
<h2>2&#65039;&#8419; เราอยู่ตรงไหนในตลาด</h2>
<div id="rank-cards"></div>
<details><summary>ดูทุกหมวด (อันดับ/ผู้เล่น/เจ้าตลาด)</summary>
<table><thead><tr><th>หมวด</th><th>อันดับเรา</th><th>ผู้เล่น</th><th>เจ้าตลาด</th></tr></thead>
<tbody id="rank-tb"></tbody></table></details>
</section>

<section>
<h2>3&#65039;&#8419; หมวดไหนกำลังโต / หด</h2>
<div id="trend-rows"></div>
<details><summary>ดูตัวเลขเทรนด์ (มูลค่า/ปี)</summary>
<table><thead><tr><th>หมวด</th><th>61-62</th><th>67-68</th><th>เปลี่ยน</th></tr></thead>
<tbody id="trend-tb"></tbody></table></details>
</section>

<section>
<h2>&#128161; โอกาส</h2>
<div class="opp"><div>หมวดที่โตแรงสุด และเรายังไม่เล่น</div>
<div class="n">{d['opportunity']['label']}</div>
<div>โต +{d['opportunity']['pct_v']}% &middot; ตลาดปัจจุบัน ~{d['opportunity']['recent_m']:,.0f} ลบ./ปี</div></div>
</section>

<footer>ข้อมูล ณ {d['build_date']} &middot; ที่มา: ระบบจัดซื้อจัดจ้างภาครัฐ (CGD/eGP)</footer>
</div>

<script>
const D = {data_json};
const baht = n => n.toLocaleString('th-TH');
new Chart(document.getElementById('mkt'), {{
  type:'doughnut',
  data:{{labels:D.market.map(m=>m.label+' '+m.pct+'%'),
    datasets:[{{data:D.market.map(m=>m.value_m),
      backgroundColor:['#C62828','#E53935','#EF5350','#F4511E','#FB8C00','#FFB300','#FDD835','#bdbdbd','#e0e0e0']}}]}},
  options:{{plugins:{{legend:{{position:'bottom',labels:{{font:{{family:'Sarabun',size:12}}}}}}}}}}
}});
document.getElementById('mkt-tb').innerHTML = D.market.map(m=>
  `<tr><td>${{m.label}}</td><td>${{baht(m.value_m)}}</td><td>${{m.pct}}%</td><td>${{m.avg_m}}</td></tr>`).join('');
const played = D.our_rank.filter(r=>r.rank);
played.sort((a,b)=>a.rank-b.rank);
document.getElementById('rank-cards').innerHTML = played.map(r=>{{
  const medal = r.rank<=15?'\\u{{1F947}}':(r.rank<=50?'\\u{{1F948}}':'\\u{{1F949}}');
  return `<div class="card"><div class="medal">${{medal}} ${{r.label}} — อันดับ ${{r.rank}} <span style="color:#777;font-weight:400">จาก ${{r.players}} ราย</span></div>
    <div style="color:#777;font-size:13px">เจ้าตลาด: ${{r.leader}} (${{r.leader_share}}%)</div></div>`;
}}).join('');
document.getElementById('rank-tb').innerHTML = D.our_rank.map(r=>
  `<tr><td>${{r.label}}</td><td>${{r.rank||'ไม่เล่น'}}</td><td>${{r.players}}</td><td>${{r.leader}} ${{r.leader_share}}%</td></tr>`).join('');
const arrow = p => p>=15?'<span class="up">\\u{{1F4C8}} โต</span>':(p<=-15?'<span class="down">\\u{{1F4C9}} หด</span>':'<span class="flat">\\u27A1\\uFE0F ทรง</span>');
document.getElementById('trend-rows').innerHTML = D.trend.map(t=>
  `<div class="rankrow"><span>${{t.label}}</span><span>${{t.pct_v>0?'+':''}}${{t.pct_v}}% ${{arrow(t.pct_v)}}</span></div>`).join('');
document.getElementById('trend-tb').innerHTML = D.trend.map(t=>
  `<tr><td>${{t.label}}</td><td>${{baht(t.early_m)}}</td><td>${{baht(t.recent_m)}}</td><td>${{t.pct_v>0?'+':''}}${{t.pct_v}}%</td></tr>`).join('');
</script>
</body>
</html>"""


def main():
    root = Path(__file__).parent.parent
    db = str(root / "data" / "winner_history.db")
    out_dir = root / "dashboard" / "parents"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = compute_data(db)
    (out_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    (out_dir / "vercel.json").write_text(
        json.dumps({"cleanUrls": True, "trailingSlash": False}, indent=2), encoding="utf-8")
    size = (out_dir / "index.html").stat().st_size
    print(f"✅ เขียน {out_dir / 'index.html'}  ({size:,} bytes)")
    print(f"ตลาด {data['total_value_m']:,.0f} ลบ. · โอกาส: {data['opportunity']['label']}")


if __name__ == "__main__":
    main()
