"""Phase 2 merge: 156 (winner_cache) + CGD → rewrite sheet tab."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client


def _f(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


# 156 จาก winner_cache (eGP-track)
base = json.load(open("data/_winner_history_156.json", encoding="utf-8"))
merged = {}
for h in base:
    merged[h["project_id"]] = {
        "province": h["province"], "district": "", "name": h["project_name"],
        "dept": h["dept"], "winner": h["winner_name"],
        "win_price": int(h["winner_price"]), "mid_price": 0,
        "discount": h["discount_pct"], "date": h["award_date"], "fy": "",
        "source": "eGP-track", "pid": h["project_id"],
    }

# CGD (เติมเฉพาะ projectId ใหม่)
try:
    cgd = json.load(open("data/_cgd_winners_raw.json", encoding="utf-8"))
except Exception:
    cgd = []
cgd_new = 0
for r in cgd:
    pid = str(r.get("รหัสโครงการ") or "").strip()
    if not pid or pid in merged:
        continue
    win = _f(r.get("ราคาตกลงซื้อ/จ้าง"))
    mid = _f(r.get("ราคากลาง(บาท)"))
    disc = round((mid - win) / mid * 100, 2) if mid > 0 and win > 0 else ""
    merged[pid] = {
        "province": (r.get("จังหวัด") or "").strip(),
        "district": (r.get("เขต/อำเภอ") or "").strip(),
        "name": (r.get("ชื่อโครงการ") or "").strip(),
        "dept": (r.get("ชื่อหน่วยงาน") or "").strip(),
        "winner": (r.get("ชื่อผู้ชนะ") or "").strip(),
        "win_price": int(win), "mid_price": int(mid), "discount": disc,
        "date": (r.get("วันที่ลงนามสัญญา") or "").strip(),
        "fy": str(r.get("ปีงบประมาณ") or "").strip(),
        "source": "CGD", "pid": pid,
    }
    cgd_new += 1

rows_d = sorted(merged.values(), key=lambda x: -x["win_price"])
from collections import Counter
print("eGP-track:", sum(1 for v in merged.values() if v["source"] == "eGP-track"),
      "| CGD ใหม่:", cgd_new, "| รวม:", len(rows_d))
print("แยกจังหวัด:", dict(Counter(v["province"] for v in rows_d)))

# เขียน sheet
gc = get_client()
sh = gc.open_by_key("1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps")
TAB = "ผลประมูลย้อนหลัง"
try:
    ws = sh.worksheet(TAB)
    ws.clear()
except Exception:
    ws = sh.add_worksheet(title=TAB, rows=len(rows_d) + 5, cols=13)

header = ["ลำดับ", "จังหวัด", "อำเภอ", "ชื่องาน", "หน่วยงาน", "ผู้ชนะ",
          "ราคาชนะ (บาท)", "ราคากลาง (บาท)", "ส่วนลด %", "วันที่", "ปีงบ", "แหล่ง", "Project ID"]
data = [header]
for i, v in enumerate(rows_d, 1):
    data.append([i, v["province"], v["district"], v["name"], v["dept"], v["winner"],
                 v["win_price"], v["mid_price"] or "", v["discount"], v["date"], v["fy"],
                 v["source"], v["pid"]])

ws.resize(rows=len(data) + 2, cols=len(header))
ws.update(values=data, range_name="A1")
ws.format("A1:M1", {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
                    "horizontalAlignment": "CENTER"})
ws.freeze(rows=1)
total = sum(v["win_price"] for v in rows_d)
print("written:", len(rows_d), "| total value:", f"{total:,}")
print("URL: https://docs.google.com/spreadsheets/d/%s/edit#gid=%s" % (sh.id, ws.id))
