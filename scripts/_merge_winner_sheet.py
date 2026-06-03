"""Phase 2 merge (v2 — fix CGD column-shift): 156 (winner_cache) + CGD adaptive → rewrite tab.
CGD egp-contract-2568 มี column shift ในบาง block → winner ดึงแบบ adaptive (field ที่มี marker
บริษัท ยกเว้นชื่องาน/หน่วยงาน). prices ใน field ชื่อตรงเชื่อถือได้ (validate). drop อำเภอ/วันที่สัญญา (shift)."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from sheets_client import get_client

MARKERS = ("บริษัท", "ห้างหุ้นส่วน", "หจก", "ห้าง", "นาย ", "นาง", "น.ส.", "ร้าน",
           "กิจการร่วมค้า", "สหกรณ์", "วิสาหกิจ", "คณะบุคคล")
SKIP_FIELDS = {"ชื่อโครงการ", "ชื่อหน่วยงาน", "ชื่อหน่วยงานย่อย", "ชื่อประเภทโครงการ",
               "วิธีจัดซื้อฯ", "กลุ่มวิธีจัดซื้อฯ"}


def _f(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def cgd_winner(r):
    for k, v in r.items():
        if k in SKIP_FIELDS:
            continue
        s = str(v)
        if any(m in s for m in MARKERS):
            return s.strip()
    return ""


# 156 จาก winner_cache (eGP-track) — เชื่อถือ 100%
base = json.load(open("data/_winner_history_156.json", encoding="utf-8"))
merged = {}
for h in base:
    yr = (h["award_date"] or "").split("/")[-1]
    merged[h["project_id"]] = {
        "province": h["province"], "name": h["project_name"], "dept": h["dept"],
        "winner": h["winner_name"], "win_price": int(h["winner_price"]), "mid_price": 0,
        "discount": h["discount_pct"], "fy": yr, "source": "eGP-track", "pid": h["project_id"],
    }

# CGD (adaptive winner + validate price)
cgd = json.load(open("data/_cgd_winners_raw.json", encoding="utf-8"))
cgd_new = cgd_skip = 0
for r in cgd:
    pid = str(r.get("รหัสโครงการ") or "").strip()
    if not pid or pid in merged:
        continue
    win_name = cgd_winner(r)
    if not win_name:
        cgd_skip += 1
        continue
    win = _f(r.get("ราคาตกลงซื้อ/จ้าง")); mid = _f(r.get("ราคากลาง(บาท)"))
    if not (win > 0 and mid > 0 and win <= mid * 1.5):
        cgd_skip += 1
        continue
    disc = round((mid - win) / mid * 100, 2)
    merged[pid] = {
        "province": (r.get("จังหวัด") or "").strip(), "name": (r.get("ชื่อโครงการ") or "").strip(),
        "dept": (r.get("ชื่อหน่วยงาน") or "").strip(), "winner": win_name,
        "win_price": int(win), "mid_price": int(mid), "discount": disc,
        "fy": str(r.get("ปีงบประมาณ") or "").strip(), "source": "CGD", "pid": pid,
    }
    cgd_new += 1

rows_d = sorted(merged.values(), key=lambda x: -x["win_price"])
from collections import Counter
print("eGP-track:", sum(1 for v in merged.values() if v["source"] == "eGP-track"),
      "| CGD ใหม่:", cgd_new, "| CGD skip (no winner/price):", cgd_skip, "| รวม:", len(rows_d))
print("แยกจังหวัด:", dict(Counter(v["province"] for v in rows_d)))

gc = get_client()
sh = gc.open_by_key("1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps")
TAB = "ผลประมูลย้อนหลัง"
ws = sh.worksheet(TAB)
ws.clear()
header = ["ลำดับ", "จังหวัด", "ชื่องาน", "หน่วยงาน", "ผู้ชนะ",
          "ราคาชนะ (บาท)", "ราคากลาง (บาท)", "ส่วนลด %", "ปีงบ", "แหล่ง", "Project ID"]
data = [header]
for i, v in enumerate(rows_d, 1):
    data.append([i, v["province"], v["name"], v["dept"], v["winner"],
                 v["win_price"], v["mid_price"] or "", v["discount"], v["fy"], v["source"], v["pid"]])
ws.resize(rows=len(data) + 2, cols=len(header))
ws.update(values=data, range_name="A1")
ws.format("A1:K1", {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5}, "horizontalAlignment": "CENTER"})
ws.freeze(rows=1)
total = sum(v["win_price"] for v in rows_d)
print("written:", len(rows_d), "| total value:", f"{total:,}")
print("URL: https://docs.google.com/spreadsheets/d/%s/edit#gid=%s" % (sh.id, ws.id))
