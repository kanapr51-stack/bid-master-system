# Parents Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** หน้าเว็บ static มือถือ สรุปวิเคราะห์ตลาดงานก่อสร้าง (size/share/trend) ส่งให้พ่อแม่ เปิดไม่ต้อง login deploy บน Vercel.

**Architecture:** Python build script อ่าน `winner_history.db` (column `work_type`) → คำนวณ (pure function `compute_data`) → render เป็น `index.html` self-contained (ข้อมูลฝัง JSON + Chart.js CDN + CSS mobile-first ขาว-แดง) → deploy Vercel static. ใช้ **primary (work_type column) ตลอด** — ไม่ import classifier.

**Tech Stack:** Python 3.14 (sqlite3 stdlib), HTML/CSS/vanilla JS, Chart.js 4 (CDN), Vercel static deploy. Test = standalone assert script (ไม่มี pytest).

**Spec:** `docs/superpowers/specs/2026-06-05-parents-dashboard-design.md`

---

## File Structure

| ไฟล์ | สร้าง/แก้ | หน้าที่ |
|---|---|---|
| `scripts/build_parents_dashboard.py` | **สร้าง** | `compute_data(db)` (pure) + `render_html(data)` + `main()` เขียนไฟล์ |
| `scripts/test_parents_dashboard.py` | **สร้าง** | assert ตัวเลข compute + HTML มี element สำคัญ |
| `dashboard/parents/index.html` | **generated** | output (ไม่เขียนมือ — build script สร้าง) |
| `dashboard/parents/vercel.json` | **สร้าง** | static deploy config |

**สี:** `--red:#C62828; --red2:#E53935; --ink:#222; --bg:#fff; --muted:#777`.

---

### Task 1: `compute_data()` + unit test (ตัวเลข)

**Files:**
- Create: `scripts/build_parents_dashboard.py` (เฉพาะ compute_data ใน task นี้)
- Create: `scripts/test_parents_dashboard.py`

- [ ] **Step 1: เขียน test ก่อน (TDD)**

สร้าง `scripts/test_parents_dashboard.py`:

```python
"""test_parents_dashboard.py — standalone assert runner (ไม่มี pytest).
รัน: python scripts/test_parents_dashboard.py → exit 0 ถ้าผ่าน, 1 ถ้า fail
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from build_parents_dashboard import compute_data  # noqa: E402

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

    # market — รวม %share ≈ 100, ถนน เป็นอันดับ 1 และ > 50%
    cats = d["market"]
    chk(abs(sum(c["pct"] for c in cats) - 100) < 1.0, "market pct sum != 100")
    top = max(cats, key=lambda c: c["value_m"])
    chk(top["cat"] == "ถนน" and top["pct"] > 50, f"top cat {top['cat']} {top['pct']}%")

    # our rank — ราง/ท่อ ต้องมี rank และดีกว่า (เลขน้อยกว่า) อาคาร
    rank = {r["cat"]: r["rank"] for r in d["our_rank"] if r["rank"]}
    chk(rank.get("รางระบายน้ำ/ท่อ") == 11, f"ราง rank={rank.get('รางระบายน้ำ/ท่อ')} != 11")

    # trend — ไฟฟ้า โต, แหล่งน้ำ หด
    tr = {t["cat"]: t["pct_v"] for t in d["trend"]}
    chk(tr.get("ไฟฟ้า/ส่องสว่าง", 0) > 100, f"ไฟฟ้า trend={tr.get('ไฟฟ้า/ส่องสว่าง')}")
    chk(tr.get("แหล่งน้ำ/ชลประทาน", 0) < 0, f"แหล่งน้ำ trend={tr.get('แหล่งน้ำ/ชลประทาน')}")

    # opportunity = core ที่เทรนด์สูงสุด และเราไม่เล่น → ไฟฟ้า
    chk(d["opportunity"]["cat"] == "ไฟฟ้า/ส่องสว่าง", f"opportunity={d['opportunity']['cat']}")

    if fails:
        print("❌ FAIL:\n" + "\n".join("  " + f for f in fails))
        sys.exit(1)
    print(f"✅ PASS — total {d['total_value_m']:,.0f} ลบ., opportunity={d['opportunity']['cat']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: รัน test ให้ FAIL**

Run: `python scripts/test_parents_dashboard.py`
Expected: FAIL — `ModuleNotFoundError` หรือ `compute_data not defined`

- [ ] **Step 3: เขียน `compute_data` ใน `scripts/build_parents_dashboard.py`**

```python
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
LABEL = {"รางระบายน้ำ/ท่อ": "ราง/ท่อ", "แหล่งน้ำ/ชลประทาน": "แหล่งน้ำ", "ไฟฟ้า/ส่องสว่าง": "ไฟฟ้า/ส่องสว่าง",
         "ดิน/ปรับพื้นที่": "ดิน"}


def short(cat):
    return LABEL.get(cat, cat)


def is_ours(w):
    return any(o in (w or "") for o in OUR)


def compute_data(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT work_type, province, fiscal_year, win_price, winner "
        "FROM winner_history WHERE work_type IS NOT NULL"
    ).fetchall()
    c.close()

    cat_n, cat_v = defaultdict(int), defaultdict(float)
    cat_win = defaultdict(lambda: defaultdict(float))   # cat -> winner(merged) -> value
    yc_v = defaultdict(lambda: defaultdict(float))       # year -> cat -> value
    years = set()
    for wt, prov, fy, wp, winner in rows:
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

    # opportunity = core เทรนด์สูงสุด ที่เราไม่เล่น (our value=0)
    our_zero = {r["cat"] for r in our_rank if r["our_value_m"] == 0}
    cands = [t for t in trend if t["cat"] in our_zero and t["pct_v"] is not None]
    opp = max(cands, key=lambda t: t["pct_v"]) if cands else trend[0]

    return {
        "total_value_m": round(total_v / 1e6, 0),
        "total_jobs": total_n,
        "year_min": min(years), "year_max": max(years),
        "market": market, "our_rank": our_rank, "trend": trend,
        "opportunity": opp,
        "build_date": datetime.now().strftime("%-d/%-m/%Y") if sys.platform != "win32"
                      else datetime.now().strftime("%d/%m/%Y"),
    }
```

- [ ] **Step 4: รัน test ให้ PASS**

Run: `set PYTHONIOENCODING=utf-8 && python scripts/test_parents_dashboard.py` (PowerShell: `$env:PYTHONIOENCODING="utf-8"; python ...`)
Expected: `✅ PASS — total 46,063 ลบ., opportunity=ไฟฟ้า/ส่องสว่าง`

ถ้า fail: อ่าน assertion. ตัวเลขมาจาก data จริง — ถ้าไม่ตรง ตรวจ query/logic (อย่าแก้ test ให้ผ่านมั่ว).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_parents_dashboard.py scripts/test_parents_dashboard.py
git commit -m "feat(dashboard): parents dashboard compute_data + test"
```

---

### Task 2: `render_html()` + `main()` (เขียนไฟล์)

**Files:**
- Modify: `scripts/build_parents_dashboard.py` (เพิ่ม render_html + main)
- Modify: `scripts/test_parents_dashboard.py` (เพิ่ม assert HTML)
- Create (generated): `dashboard/parents/index.html`, `dashboard/parents/vercel.json`

- [ ] **Step 1: เพิ่ม assert HTML ใน test**

แก้ `scripts/test_parents_dashboard.py` — เพิ่มก่อน `if fails:`:

```python
    # render HTML
    from build_parents_dashboard import render_html
    html = render_html(d)
    chk("สรุปผลการวิเคราะห์ตลาดงานก่อสร้าง" in html, "ไม่มีหัวเว็บ")
    chk("จัดทำโดยน้องกัญจน์" in html, "ไม่มีเครดิตน้องกัญจน์")
    chk('name="robots" content="noindex"' in html, "ไม่มี noindex")
    chk("chart.js" in html.lower() or "chart.umd" in html.lower(), "ไม่มี Chart.js")
    chk("#C62828" in html or "#c62828" in html.lower(), "ไม่มีสีแดงธีม")
    chk("46,063" in html or "46063" in html.replace(",", ""), "ไม่มีตัวเลขตลาดรวม")
    chk("ไฟฟ้า" in html, "ไม่มีหมวดไฟฟ้า")
    chk(len(html) > 4000, f"HTML สั้นผิดปกติ ({len(html)} ตัว)")
```

- [ ] **Step 2: รัน test ให้ FAIL (render_html ยังไม่มี)**

Run: `$env:PYTHONIOENCODING="utf-8"; python scripts/test_parents_dashboard.py`
Expected: FAIL — `cannot import name 'render_html'`

- [ ] **Step 3: เพิ่ม `render_html` + `main` ใน `build_parents_dashboard.py`**

ต่อท้ายไฟล์ (ก่อน `if __name__`):

```python
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
.card .n{{font-size:22px;font-weight:700;color:var(--red);}}
.rankrow{{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);}}
.rankrow:last-child{{border:0;}}
.medal{{font-size:15px;font-weight:700;}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px;}}
th,td{{text-align:right;padding:7px 6px;border-bottom:1px solid var(--line);}}
th:first-child,td:first-child{{text-align:left;}}
th{{background:var(--red);color:#fff;font-weight:600;}}
details{{margin-top:10px;}}
summary{{color:var(--red);font-weight:600;cursor:pointer;padding:8px 0;list-style:none;}}
summary::after{{content:" ▸";}}
details[open] summary::after{{content:" ▾";}}
.opp{{background:linear-gradient(135deg,var(--red),var(--red2));color:#fff;border-radius:14px;padding:20px;text-align:center;}}
.opp .n{{font-size:30px;font-weight:700;}}
.up{{color:#2e7d32;font-weight:700;}}.down{{color:var(--red);font-weight:700;}}.flat{{color:var(--muted);}}
footer{{text-align:center;color:var(--muted);font-size:12px;padding:20px;}}
canvas{{max-width:100%;}}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>{title_full}</h1>
<div class="big">{d['total_value_m']:,.0f}<small>มูลค่าตลาดรวม (ล้านบาท) · {d['total_jobs']:,} งาน</small></div>
</header>

<section>
<h2>1️⃣ ตลาดใหญ่แค่ไหน — แยกตามหมวดงาน</h2>
<canvas id="mkt" height="220"></canvas>
<details><summary>ดูตารางเต็ม</summary>
<table><thead><tr><th>หมวด</th><th>มูลค่า (ลบ.)</th><th>%</th><th>เฉลี่ย/งาน</th></tr></thead>
<tbody id="mkt-tb"></tbody></table></details>
</section>

<section>
<h2>2️⃣ เราอยู่ตรงไหนในตลาด</h2>
<div id="rank-cards"></div>
<details><summary>ดูทุกหมวด (อันดับ/ส่วนแบ่ง/เจ้าตลาด)</summary>
<table><thead><tr><th>หมวด</th><th>อันดับเรา</th><th>ผู้เล่น</th><th>เจ้าตลาด</th></tr></thead>
<tbody id="rank-tb"></tbody></table></details>
</section>

<section>
<h2>3️⃣ หมวดไหนกำลังโต / หด</h2>
<div id="trend-rows"></div>
<details><summary>ดูตัวเลขเทรนด์</summary>
<table><thead><tr><th>หมวด</th><th>61-62</th><th>67-68</th><th>เปลี่ยน</th></tr></thead>
<tbody id="trend-tb"></tbody></table></details>
</section>

<section>
<h2>💡 โอกาส</h2>
<div class="opp"><div>หมวดที่โตแรงสุด และเรายังไม่เล่น</div>
<div class="n">{d['opportunity']['label']}</div>
<div>มูลค่าโต +{d['opportunity']['pct_v']}% (เทียบ 61-62 → 67-68)</div></div>
</section>

<footer>ข้อมูล ณ {d['build_date']} · ที่มา: ระบบจัดซื้อจัดจ้างภาครัฐ (CGD/eGP)</footer>
</div>

<script>
const D = {data_json};
const baht = n => n.toLocaleString('th-TH');
// 1) market donut
new Chart(document.getElementById('mkt'), {{
  type:'doughnut',
  data:{{labels:D.market.map(m=>m.label+' '+m.pct+'%'),
    datasets:[{{data:D.market.map(m=>m.value_m),
      backgroundColor:['#C62828','#E53935','#EF5350','#F4511E','#FB8C00','#FFB300','#FDD835','#bdbdbd','#e0e0e0']}}]}},
  options:{{plugins:{{legend:{{position:'bottom',labels:{{font:{{family:'Sarabun',size:12}}}}}}}}}}
}});
document.getElementById('mkt-tb').innerHTML = D.market.map(m=>
  `<tr><td>${{m.label}}</td><td>${{baht(m.value_m)}}</td><td>${{m.pct}}%</td><td>${{m.avg_m}}</td></tr>`).join('');
// 2) rank cards (เฉพาะหมวดที่เราเล่น = มี rank)
const played = D.our_rank.filter(r=>r.rank);
played.sort((a,b)=>a.rank-b.rank);
document.getElementById('rank-cards').innerHTML = played.map(r=>{{
  const medal = r.rank<=15?'🥇':(r.rank<=50?'🥈':'🥉');
  return `<div class="card"><div class="medal">${{medal}} ${{r.label}} — อันดับ ${{r.rank}} <span style="color:#777;font-weight:400">จาก ${{r.players}} ราย</span></div>
    <div style="color:#777;font-size:13px">เจ้าตลาด: ${{r.leader}} (${{r.leader_share}}%)</div></div>`;
}}).join('');
document.getElementById('rank-tb').innerHTML = D.our_rank.map(r=>
  `<tr><td>${{r.label}}</td><td>${{r.rank||'ไม่เล่น'}}</td><td>${{r.players}}</td><td>${{r.leader}} ${{r.leader_share}}%</td></tr>`).join('');
// 3) trend rows
const arrow = p => p>=15?'<span class="up">📈 โต</span>':(p<=-15?'<span class="down">📉 หด</span>':'<span class="flat">➡️ ทรง</span>');
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
    print(f"✅ เขียน {out_dir/'index.html'}  ({d_size(out_dir)} bytes)")
    print(f"ตลาด {data['total_value_m']:,.0f} ลบ. · โอกาส: {data['opportunity']['label']}")


def d_size(p):
    return (p / "index.html").stat().st_size
```

- [ ] **Step 4: รัน build + test**

Run:
```
$env:PYTHONIOENCODING="utf-8"; python scripts/build_parents_dashboard.py; python scripts/test_parents_dashboard.py
```
Expected: build เขียนไฟล์ + `✅ PASS`. ไฟล์ `dashboard/parents/index.html` เกิดขึ้น.

- [ ] **Step 5: เปิดดูในเบราว์เซอร์ (sanity ภาพ)**

Run: `start dashboard/parents/index.html` (Windows) — ตรวจด้วยตา: หัวเว็บ, โดนัทชาร์ต, การ์ดอันดับ, เทรนด์, callout โอกาส แสดงครบ + โทนขาว-แดง + responsive (ย่อหน้าต่างแคบดู mobile).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_parents_dashboard.py scripts/test_parents_dashboard.py dashboard/parents/index.html dashboard/parents/vercel.json
git commit -m "feat(dashboard): render parents dashboard HTML (ขาว-แดง mobile)"
```

---

### Task 3: Deploy ขึ้น Vercel

**Files:** ใช้ `dashboard/parents/`

- [ ] **Step 1: ตรวจ Vercel CLI + login**

Run: `vercel whoami`
- ถ้าได้ชื่อ user → ผ่าน. ถ้า error/ไม่ login → บอกผู้ใช้รัน `vercel login` ใน terminal เอง (`! vercel login`) แล้วค่อยต่อ.

- [ ] **Step 2: Deploy production**

Run: `vercel deploy dashboard/parents --prod --yes`
Expected: ได้ URL `https://<project>.vercel.app`. คัดลอก URL.

ถ้าถามชื่อ project ครั้งแรก → ตั้งชื่อ `parents-market-dashboard` (หรือชื่อที่เดาไม่ได้).

- [ ] **Step 3: ตรวจ deploy live**

Run: `curl -s -o NUL -w "%{http_code}" https://<url>` → Expected `200`.
เปิด URL บนเบราว์เซอร์/มือถือ ตรวจแสดงผลถูก.

- [ ] **Step 4: ส่ง Discord + จด URL**

```python
import sys; sys.path.insert(0, 'scripts')
from Sebastian_Discord_Notify import load_env, get_credentials, send
load_env(); token, ch = get_credentials()
send(token, ch, "✅ เว็บแดชบอร์ดพ่อแม่ deploy แล้ว: <url>")
```

- [ ] **Step 5: รายงาน URL ให้คุณกัญจน์** เพื่อส่งต่อให้พ่อแม่ทาง LINE.

---

## Self-Review

**Spec coverage:**
- §1 mobile static ไม่ login → static HTML + Vercel ✓ (Task 2-3)
- §3 file structure (build script/html/vercel.json) → Task 1-2 ✓
- §4 data (hero/size/share/trend/opportunity, ดึงสด) → compute_data ✓ (Task 1). **หมายเหตุ: ใช้ primary ตลอด** (ปรับจาก §4 ที่เขียน involvement สำหรับ our-rank — primary consistent กับเลข #11 ที่ confirm แล้ว)
- §5 layout 6 ส่วน + expand `<details>` + ธีมขาว-แดง + หัวเว็บ "จัดทำโดยน้องกัญจน์" → render_html ✓ (Task 2)
- §6 deploy Vercel + noindex → Task 3 + meta robots ✓
- §7 out of scope (no login/live/multi-page) → ไม่มี task ✓

**Placeholder scan:** `<url>` ใน Task 3 = runtime value (ได้จาก deploy) ไม่ใช่ placeholder. ไม่มี TBD/TODO.

**Type consistency:** `compute_data` คืน dict keys (total_value_m, total_jobs, year_min/max, market[], our_rank[], trend[], opportunity, build_date) — ใช้ตรงกันใน render_html + test. field ต่อ item (cat/label/value_m/pct/avg_m, rank/players/leader/leader_share, early_m/recent_m/pct_v) สม่ำเสมอ. ✓
