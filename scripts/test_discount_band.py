# -*- coding: utf-8 -*-
"""test_discount_band.py — predict_band (fail-open/gate/mapping) + save_ml_band + job_detail wiring.
ใช้โมเดลจริงใน data/models (เทรนโดย train_discount_band.py) — ถ้ายังไม่เทรนจะ FAIL ชัดๆ."""
import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

from discount_band import predict_band, _map_dept

# --- predict_band: เคสในเขต 4 จังหวัด ---
b = predict_band("จ้างก่อสร้างถนนคอนกรีตเสริมเหล็ก บ้านดอนแดง", 5_000_000,
                 "องค์การบริหารส่วนตำบลหนองแวง", "นครพนม", "69079999999")
assert b is not None, "ควรได้ band สำหรับงานในเขต"
assert 0 <= b["disc_p50"] <= b["disc_p80"] <= 70, b            # ไม่ crossing + ช่วง sane
assert b["price_p80"] <= b["price_p50"] <= 5_000_000, b        # ลดมากกว่า → ราคาต่ำกว่า
assert abs(b["price_p80"] - 5_000_000 * (1 - b["disc_p80"] / 100)) < 2, b
assert b["version"].startswith("band-"), b
print("OK predict_band in-scope")

# --- gate: นอก 4 จังหวัด → None ---
assert predict_band("จ้างก่อสร้างถนน", 5_000_000, "อบต.ใดๆ", "เชียงใหม่", "69079999998") is None
print("OK province gate")

# --- fail-open: input ขาด ---
assert predict_band("", 1_000_000, "", "นครพนม", "") is None
assert predict_band("งานถนน", 0, "", "นครพนม", "") is None
assert predict_band("งานถนน", None, "", "นครพนม", "") is None
print("OK fail-open inputs")

# --- pid parse ไม่ได้ → fallback เดือนปัจจุบัน (ยังได้ band) ---
b2 = predict_band("จ้างก่อสร้างถนน คสล.", 1_000_000, "เทศบาลตำบลบ้านแพง", "นครพนม", "")
assert b2 is not None, "pid ว่างต้อง fallback ได้"
print("OK pid fallback")

# --- dept mapping: exact / prefix / unmapped ---
vocab = ["การประปาส่วนภูมิภาค", "กรมทางหลวง", "เทศบาลตำบลบ้านแพง"]
assert _map_dept("กรมทางหลวง", vocab) == "กรมทางหลวง"
assert _map_dept("การประปาส่วนภูมิภาคสาขาธาตุพนม", vocab) == "การประปาส่วนภูมิภาค"
assert _map_dept("ศูนย์อะไรสักอย่าง", vocab) is None
assert _map_dept("", vocab) is None
print("OK dept mapping")

# --- save_ml_band: upsert เฉพาะ ml_* ไม่ทับ area_* ---
c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.execute("""CREATE TABLE price_predictions (
    project_id TEXT PRIMARY KEY, budget INTEGER,
    area_disc_lo REAL, area_price_lo INTEGER, predicted_at TEXT,
    ml_disc_p50 REAL, ml_disc_p80 REAL, ml_price_p50 INTEGER, ml_price_p80 INTEGER,
    ml_version TEXT, ml_predicted_at TEXT)""")
c.execute("INSERT INTO price_predictions (project_id, budget, area_disc_lo, area_price_lo, predicted_at) "
          "VALUES ('P1', 1000000, 12.5, 875000, '2026-07-01')")
from Sebastian_Customer_DB import save_ml_band
band = {"disc_p50": 10.0, "disc_p80": 20.0, "price_p50": 900000, "price_p80": 800000,
        "version": "band-test"}
save_ml_band("P1", band, conn=c)                       # upsert งานที่มี B′ อยู่แล้ว
r = c.execute("SELECT * FROM price_predictions WHERE project_id='P1'").fetchone()
assert r["ml_disc_p80"] == 20.0 and r["ml_version"] == "band-test", dict(r)
assert r["area_disc_lo"] == 12.5 and r["budget"] == 1000000, "ห้ามทับคอลัมน์ B′"
assert r["predicted_at"] == "2026-07-01", "ห้ามแตะ predicted_at ของ B′"
save_ml_band("P2", band, conn=c)                       # insert งานใหม่ (ไม่มีแถวเดิม)
r2 = c.execute("SELECT ml_price_p80 FROM price_predictions WHERE project_id='P2'").fetchone()
assert r2["ml_price_p80"] == 800000, dict(r2)
band2 = dict(band, disc_p80=25.0)
save_ml_band("P1", band2, conn=c)                      # upsert ซ้ำ → ค่าล่าสุด
assert c.execute("SELECT ml_disc_p80 FROM price_predictions WHERE project_id='P1'").fetchone()[0] == 25.0
print("OK save_ml_band")

# --- job_detail มี key ml_band + persist fail เงียบบน schema เก่า ---
import portal_views as pv
c2 = sqlite3.connect(":memory:")
c2.row_factory = sqlite3.Row
c2.execute("CREATE TABLE projects_seen(project_id TEXT, project_name TEXT, budget REAL, province TEXT)")
c2.execute("CREATE TABLE bid_results(project_id TEXT, bidder_name TEXT, bidder_tin TEXT, "
           "price_proposal TEXT, price_agree TEXT, is_winner INT, is_sme INT)")
c2.execute("CREATE TABLE project_locations(project_id TEXT, moi_name TEXT, province_name TEXT, "
           "deadline TEXT, deadline_time TEXT)")
c2.execute("CREATE TABLE price_predictions(project_id TEXT, area_price_lo REAL, area_price_hi REAL)")
c2.execute("INSERT INTO projects_seen VALUES ('69010000001','จ้างก่อสร้างถนน คสล. สายทดสอบ',1000000,'นครพนม')")
d = pv.job_detail(c2, "69010000001")
assert "ml_band" in d, "job_detail ต้องมี key ml_band"
assert d["ml_band"] is not None and d["ml_band"]["disc_p80"] >= d["ml_band"]["disc_p50"], d["ml_band"]
# schema test ไม่มี ml_ columns + ไม่มี PK → persist ล้มเงียบ แต่ display ต้องรอด (assert ด้านบนพิสูจน์แล้ว)
d_none = pv.job_detail(c2, "NOPE")
assert d_none is None
print("OK job_detail ml_band wiring")

print("✅ test_discount_band ผ่านทั้งหมด")
