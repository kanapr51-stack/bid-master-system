"""test_portal_views.py — job_detail + company_profile + render (Portal detail/company)."""
import os, sys, sqlite3, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import portal_views as pv


def _seed():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE projects_seen(project_id TEXT, project_name TEXT, budget REAL, province TEXT)")
    c.execute("CREATE TABLE bid_results(project_id TEXT, bidder_name TEXT, bidder_tin TEXT, "
              "price_proposal TEXT, price_agree TEXT, is_winner INT, is_sme INT)")
    c.execute("CREATE TABLE project_locations(project_id TEXT, moi_name TEXT, province_name TEXT, deadline TEXT)")
    c.execute("CREATE TABLE price_predictions(project_id TEXT, area_price_lo REAL, area_price_hi REAL)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000001','งานถนน A',1000000,'นครพนม')")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0)")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.บี','T2','800000','',0,1)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000002','งานไม่มีราคากลาง',0,'บึงกาฬ')")
    c.execute("INSERT INTO bid_results VALUES ('69010000002','หจก.เอ','T1','500000','',0,0)")
    # งานประมูล (D0) ยังไม่มีผู้ยื่น — มี deadline + คาดราคา
    c.execute("INSERT INTO projects_seen VALUES ('69010000009','งานประมูลใหม่',1500000,'นครพนม')")
    c.execute("INSERT INTO project_locations VALUES ('69010000009','','นครพนม','2027-12-31')")
    c.execute("INSERT INTO price_predictions VALUES ('69010000009',1200000,1400000)")
    return c


# --- job_detail ---
c = _seed()
d = pv.job_detail(c, "69010000001")
assert d["job"]["budget"] == 1000000 and d["job"]["name"] == "งานถนน A", d["job"]
assert len(d["bidders"]) == 2, d["bidders"]
assert d["bidders"][0]["is_winner"] and d["bidders"][0]["name"] == "หจก.เอ", d["bidders"]
assert d["bidders"][0]["discount"] == 10.0, d["bidders"][0]      # 1 - 900000/1000000
assert d["bidders"][1]["is_sme"] is True, d["bidders"][1]
d2 = pv.job_detail(c, "69010000002")
assert d2["bidders"][0]["discount"] is None, d2                  # budget=0
assert pv.job_detail(c, "NOPE") is None
print("OK job_detail")

# --- company_profile ---
c = _seed()
c.execute("INSERT INTO projects_seen VALUES ('68010000003','งานเก่า',2000000,'นครพนม')")
c.execute("INSERT INTO bid_results VALUES ('68010000003','หจก.เอ','T1','1600000','1600000',1,0)")
p = pv.company_profile(c, "T1")
assert p["name"] == "หจก.เอ" and p["total_bids"] == 3, p          # T1 อยู่ 3 งาน
assert p["wins"] == 2 and p["win_rate"] == round(2/3*100, 1), p
assert set(p["provinces"]) == {"นครพนม", "บึงกาฬ"}, p["provinces"]
years = [g["year"] for g in p["by_year"]]
assert years == [2569, 2568], years                              # ใหม่→เก่า
assert sum(g["bids"] for g in p["by_year"]) == p["total_bids"], p["by_year"]
assert p["discount_avg"] is not None, p
assert sum(h["count"] for h in p["discount_hist"]) >= 1, p["discount_hist"]
assert pv.company_profile(c, "NOPE") is None
print("OK company_profile")

# --- render_job_page ---
c = _seed()
d = pv.job_detail(c, "69010000001")
h = pv.render_job_page(d, "TOK", 2000000000)
assert "งานถนน A" in h and "🆔 69010000001" in h, h
assert "ราคากลาง 1,000,000" in h, h
assert "/portal/company?t=TOK&tin=T1" in h and "from=69010000001" in h, h   # ลิงก์บริษัท
assert "ส่วนลด 10.0%" in h, h
assert "/portal?t=TOK" in h, "ไม่มีปุ่มกลับ"
h0 = pv.render_job_page(None, "TOK", 0)
assert "ไม่พบรายละเอียดงานนี้" in h0, h0
print("OK render_job_page")

# --- render_job_page: งานประมูลยังไม่มีผู้ยื่น (deadline + คาดราคา + stage-aware) ---
c = _seed()
db = pv.job_detail(c, "69010000009")
assert db["bidders"] == [] and db["job"]["deadline"] == "2027-12-31", db["job"]
assert db["job"]["pred_lo"] == 1200000 and db["job"]["pred_hi"] == 1400000, db["job"]
hb = pv.render_job_page(db, "TOK", 0)
assert "ยังไม่มีผู้ยื่น" in hb, hb
assert "ยื่นซอง 31 ธ.ค. 2570" in hb and "เหลืออีก" in hb, hb          # countdown
assert "คาดราคา 1,200,000–1,400,000" in hb, hb
assert "ผู้ยื่นทั้งหมด" not in hb, hb                                # ไม่โชว์ตารางผู้ยื่น
print("OK render_job_page_bidding")

# --- render_company_page ---
c = _seed()
c.execute("INSERT INTO projects_seen VALUES ('68010000003','งานเก่า',2000000,'นครพนม')")
c.execute("INSERT INTO bid_results VALUES ('68010000003','หจก.เอ','T1','1600000','1600000',1,0)")
p = pv.company_profile(c, "T1")
h = pv.render_company_page(p, "TOK", "69010000001", 2000000000)
assert "หจก.เอ" in h, h
assert "ยื่น" in h and "ชนะ" in h and "win-rate" in h, h          # stat cards
assert "ปี 2569" in h and "ปี 2568" in h, h                       # timeline แยกปี
assert "class=\"fill\"" in h, "ไม่มีกราฟ bar"
assert "/portal/job?t=TOK&pid=69010000001" in h, "ปุ่มกลับไปงานเดิม"
assert "/portal/job?t=TOK&pid=68010000003" in h, "ลิงก์งานใน timeline"
h0 = pv.render_company_page(None, "TOK", "", 0)
assert "ไม่พบประวัติบริษัทนี้" in h0, h0
print("OK render_company_page")

# --- render_job_page: ไทม์ไลน์ของฉัน (รางรถไฟ) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
notes = [{"id": 7, "entry_date": "2026-01-21", "note": "โทรหาช่าง <x>"}]
ht = pv.render_job_page(d, "TOK", 0, notes)
assert "🚂 ไทม์ไลน์ของฉัน" in ht, ht
assert "action=\"/portal/job/note\"" in ht and "type=\"date\"" in ht, ht   # ฟอร์มเพิ่ม
assert "21 ม.ค. 2569" in ht, ht                                            # วันที่ไทยบนราง
assert "โทรหาช่าง &lt;x&gt;" in ht, "escape โน้ตผิด"
assert "value=\"7\"" in ht, "ไม่มี note_id ในฟอร์มแก้/ลบ"
ht0 = pv.render_job_page(d, "TOK", 0, [])
assert "ยังไม่มีรายการ" in ht0, ht0
# ส่วนผู้ยื่นเดิมยังอยู่
assert "ผู้ยื่นทั้งหมด" in ht, ht
print("OK render_job_page_timeline")

# --- render_job_page: โน้ตภาพรวม (free-form textarea) ---
hov = pv.render_job_page(d, "TOK", 0, [], "งบ 1.5 ล้าน <ติดต่อโยธา>")
assert "📝 โน้ตภาพรวม" in hov, hov
assert "name=\"action\" value=\"save_overview\"" in hov, hov
assert "<textarea" in hov and "งบ 1.5 ล้าน &lt;ติดต่อโยธา&gt;" in hov, "ต้อง prefilled + escape"
# ไม่มีโน้ตภาพรวม → textarea ว่าง (ยังมี section)
hov0 = pv.render_job_page(d, "TOK", 0, [])
assert "📝 โน้ตภาพรวม" in hov0 and "<textarea" in hov0, hov0
print("OK render_job_page_overview")

# --- head_to_head (เทียบเรา vs คู่แข่ง เฉพาะงานที่ยื่นด้วยกัน) ---
c = _seed()   # 69010000001: T1(ชนะ 900k) + T2(800k) ยื่นด้วยกัน
h = pv.head_to_head(c, "T1", "T2")
assert h["shared"] == 1 and h["our_wins"] == 1 and h["their_wins"] == 0, h
assert h["jobs"][0]["winner_side"] == "us", h
assert h["jobs"][0]["our_price"] == 900000.0 and h["jobs"][0]["their_price"] == 800000.0, h
assert h["our_name"] == "หจก.เอ", h
assert pv.head_to_head(c, "T1", "T1") is None, "tin เดียวกันต้อง None"
assert pv.head_to_head(c, None, "T2") is None
assert pv.head_to_head(c, "T1", "TZZZ") is None, "ไม่เจอกันต้อง None"
print("OK head_to_head")

# render company page + h2h section
p = pv.company_profile(c, "T2")
hc = pv.render_company_page(p, "TOK", "69010000001", 0, h)
assert "⚔️ เทียบกับ หจก.เอ" in hc and "เจอกัน" in hc, hc
assert "🟢 เราชนะ" in hc, hc
hc0 = pv.render_company_page(p, "TOK", "69010000001", 0, None)
assert "⚔️" not in hc0, "ไม่มี h2h ต้องไม่โชว์ section"
print("OK render_company_h2h")

# --- won_portfolio (ผลงานที่ชนะ ทุกวิธีจัดซื้อ จาก cgd_winners — join ด้วยชื่อ) ---
# CGD เก็บชื่อเต็ม 'ห้างหุ้นส่วนจำกัด เอ' / eGP ย่อ 'หจก.เอ' → normalized exact ต้อง match
_W = "ห้างหุ้นส่วนจำกัด เอ"
def _seed_won():
    c = _seed()
    c.execute("CREATE TABLE cgd_winners(project_id TEXT, project_name TEXT, winner TEXT, "
              "winner_tin TEXT, budget REAL, win_price REAL, proc_type TEXT)")
    def ins(pid, nm, w, b, wp, pt):
        c.execute("INSERT INTO cgd_winners VALUES (?,?,?,?,?,?,?)", (pid, nm, w, "เพี้ยน", b, wp, pt))
    ins('69020000001', 'ถนน e-bidding', _W, 1000000, 900000, 'ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)')
    ins('69020000002', 'อาคารเฉพาะเจาะจง', _W, 2000000, 2000000, 'เฉพาะเจาะจง')
    ins('68020000003', 'ซ่อมสอบราคา', _W, 600000, 500000, 'สอบราคา')
    ins('69020000004', 'งานพิเศษ', _W, 300000, 300000, 'พิเศษ')
    ins('69020000009', 'งานบริษัทอื่น', 'ห้างหุ้นส่วนจำกัด เอบีซี', 9000000, 9000000, 'เฉพาะเจาะจง')
    return c

c = _seed_won()
w = pv.won_portfolio(c, "หจก.เอ")                                     # eGP ย่อ → ต้อง match _W
assert w["total"]["count"] == 4 and w["total"]["value"] == 3700000, w["total"]   # ไม่นับ 'เอบีซี'
assert w["groups"]["bid"]["count"] == 2 and w["groups"]["bid"]["value"] == 1400000, w["groups"]
assert w["groups"]["specific"]["count"] == 1 and w["groups"]["specific"]["value"] == 2000000, w["groups"]
assert w["groups"]["other"]["count"] == 1, w["groups"]                # 'พิเศษ' → other
assert w["top_overall"]["price"] == 2000000 and "เฉพาะเจาะจง" in w["top_overall"]["name"], w["top_overall"]
assert w["top_bid"]["price"] == 900000, w["top_bid"]                  # สูงสุดของประมูล
assert w["top_nonbid"]["price"] == 2000000, w["top_nonbid"]           # สูงสุดของวิธีอื่น (specific+other)
assert [j["price"] for j in w["jobs"]] == [2000000, 900000, 500000, 300000], w["jobs"]   # เรียงมาก→น้อย
# normalized exact: 'เอบีซี' ต้องไม่ปนเข้า 'เอ' (กัน substring ผิด)
wabc = pv.won_portfolio(c, "ห้างหุ้นส่วนจำกัด เอบีซี")
assert wabc["total"]["count"] == 1 and wabc["total"]["value"] == 9000000, wabc["total"]
# filter proc
wb = pv.won_portfolio(c, "หจก.เอ", "bid")
assert len(wb["jobs"]) == 2 and all(j["group"] == "bid" for j in wb["jobs"]), wb["jobs"]
ws = pv.won_portfolio(c, "หจก.เอ", "specific")
assert len(ws["jobs"]) == 1, ws["jobs"]
assert wb["groups"]["bid"]["count"] == 2, "stats ต้องเต็มเสมอ ไม่ขึ้นกับ filter"   # filter กรองแค่ job list
assert pv.won_portfolio(c, "หจก.ไม่มีจริง") is None
assert pv.won_portfolio(c, "จำกัด") is None                          # ชื่อเหลือแกน '' → None
# ไม่มีตาราง cgd_winners → None (degrade gracefully)
assert pv.won_portfolio(_seed(), "หจก.เอ") is None
print("OK won_portfolio")

# render company page + won section + filter chips
c = _seed_won()
p = pv.company_profile(c, "T1")    # T1 ชื่อ 'หจก.เอ' (จาก bid_results)
w = pv.won_portfolio(c, p["name"])
hw = pv.render_company_page(p, "TOK", "69010000001", 0, None, w)
assert "🏆 ผลงานที่ชนะ" in hw, hw
assert "ประมูล" in hw and "เจาะจง" in hw, hw                          # stat ประมูล vs เจาะจง
assert "💎" in hw and "อาคารเฉพาะเจาะจง" in hw, "งานมูลค่าสูงสุด"
assert "proc=bid" in hw and "proc=specific" in hw and "proc=all" in hw, "filter chips"
# ลำดับ: 🏆 ต้องอยู่หลังกราฟ ยื่น–ชนะ + ส่วนลด
assert hw.index("🏆 ผลงานที่ชนะ") > hw.index("💸 ส่วนลดที่ชอบเสนอ") > hw.index("📊 ยื่น–ชนะ รายปี"), "ลำดับผิด"
# รายชื่องานซ่อนใน <details> (proc=all → ปิด) — 'ซ่อมสอบราคา' อยู่ในลิสต์เท่านั้น
assert "<details class=\"wonlist\">" in hw and "ดูรายชื่องาน" in hw, "ต้องมี details (ปิด)"
assert hw.index("ซ่อมสอบราคา") > hw.index("<details"), "ชื่องานต้องอยู่ใน details"
# filter อยู่ (proc != all) → details เปิดอัตโนมัติ
wb = pv.won_portfolio(c, p["name"], "bid")
hwb = pv.render_company_page(p, "TOK", "69010000001", 0, None, wb)
assert "<details class=\"wonlist\" open>" in hwb, "filter → details เปิด"
hw0 = pv.render_company_page(p, "TOK", "69010000001", 0, None, None)
assert "🏆 ผลงานที่ชนะ" not in hw0, "ไม่มี won → ไม่โชว์ section"
print("OK render_company_won")
print("OK test_portal_views")
