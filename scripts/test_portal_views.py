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
    c.execute("CREATE TABLE project_locations(project_id TEXT, moi_name TEXT, province_name TEXT, deadline TEXT, deadline_time TEXT)")
    c.execute("CREATE TABLE price_predictions(project_id TEXT, area_price_lo REAL, area_price_hi REAL)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000001','งานถนน A',1000000,'นครพนม')")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.เอ','T1','900000','900000',1,0)")
    c.execute("INSERT INTO bid_results VALUES ('69010000001','หจก.บี','T2','800000','',0,1)")
    c.execute("INSERT INTO projects_seen VALUES ('69010000002','งานไม่มีราคากลาง',0,'บึงกาฬ')")
    c.execute("INSERT INTO bid_results VALUES ('69010000002','หจก.เอ','T1','500000','',0,0)")
    # งานประมูล (D0) ยังไม่มีผู้ยื่น — มี deadline + คาดราคา
    c.execute("INSERT INTO projects_seen VALUES ('69010000009','งานประมูลใหม่',1500000,'นครพนม')")
    c.execute("INSERT INTO project_locations VALUES ('69010000009','','นครพนม','2027-12-31','13.00-16.00 น.')")
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
assert db["job"]["deadline_time"] == "13.00-16.00 น.", db["job"]
assert db["job"]["pred_lo"] == 1200000 and db["job"]["pred_hi"] == 1400000, db["job"]
hb = pv.render_job_page(db, "TOK", 0)
assert "ยังไม่มีผู้ยื่น" in hb, hb
assert "ยื่นซอง 31 ธ.ค. 2570 13.00-16.00 น." in hb and "เหลืออีก" in hb, hb          # countdown + เวลา
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
              "winner_tin TEXT, budget REAL, win_price REAL, proc_type TEXT, normalized_winner TEXT)")
    def ins(pid, nm, w, b, wp, pt):
        c.execute("INSERT INTO cgd_winners VALUES (?,?,?,?,?,?,?,?)",
                  (pid, nm, w, "เพี้ยน", b, wp, pt, pv._norm_name(w)))
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

# --- render_job_page: ปุ่มดาว "ที่สนใจ" (ชั้นที่ 2, แยกจาก ⭐ ติดตามเดิม) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
h_on = pv.render_job_page(d, "TOK", 0, [], "", True)
assert "⭐" in h_on, "ติดดาวแล้วต้องโชว์ ⭐ เต็ม"
assert "/portal/star_toggle?t=TOK&pid=69010000001&back=job" in h_on, h_on
h_off = pv.render_job_page(d, "TOK", 0, [], "", False)
assert "☆" in h_off and "star_toggle" in h_off, "ไม่ติดดาวต้องโชว์ ☆ ว่าง"
print("OK render_job_page_star")

# --- job_detail: intel_lines (cgd_intel wiring — value-add, must degrade gracefully) ---
import cgd_intel
_orig_intel_context = cgd_intel.intel_context

cgd_intel.intel_context = lambda *a, **k: {"lines": ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"]}
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] == ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"], d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_present")

cgd_intel.intel_context = lambda *a, **k: None
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] is None, d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_none")

def _raise_intel(*a, **k):
    raise RuntimeError("boom")
cgd_intel.intel_context = _raise_intel
try:
    c = _seed()
    d = pv.job_detail(c, "69010000001")
    assert d["intel_lines"] is None, d["intel_lines"]
finally:
    cgd_intel.intel_context = _orig_intel_context
print("OK job_detail_intel_lines_error_safe")

# dept_name (when the column exists) must reach cgd_intel.intel_context as the 3rd positional arg
captured = {}
def _capture_intel(province, project_name, dept_name, project_id, budget, conn=None):
    captured["dept_name"] = dept_name
    return None
cgd_intel.intel_context = _capture_intel
try:
    c = _seed()
    c.execute("ALTER TABLE projects_seen ADD COLUMN dept_name TEXT")
    c.execute("UPDATE projects_seen SET dept_name='อบต.ทดสอบ' WHERE project_id='69010000001'")
    pv.job_detail(c, "69010000001")
finally:
    cgd_intel.intel_context = _orig_intel_context
assert captured["dept_name"] == "อบต.ทดสอบ", captured
print("OK job_detail_dept_name_passthrough")


def test_job_detail_custom_calc():
    orig_ctx = cgd_intel.intel_context
    orig_calc = cgd_intel.calc_custom_winrate
    cgd_intel.intel_context = lambda *a, **k: {
        "lines": [], "amphoe": "นาทม",
        "company_tables": [{"label": "x", "n": 5, "conf_tag": "🟢 มั่นใจ",
                            "p25": 10.0, "p75": 20.0, "median": 15.0,
                            "companies": [{"name": "หจก.A", "tin": "1", "games": 3, "median": 12.0,
                                           "p25": 10.0, "p75": 15.0, "project_ids": ["K0"]}]}],
        "winrate_table": None, "scope_rows": [],
        "predicted_attendees": {"probs": {"หจก.A": 0.7}, "conf": None, "n_auctions": 8}, }
    captured = {}
    def fake_calc(conn, province, tokens, project_name, dept_name, district,
                  my_price, budget, selected_names, extra_names, attend_probs=None):
        captured.update(province=province, tokens=tokens, district=district,
                        my_price=my_price, selected=selected_names, attend=attend_probs)
        return {"my_discount_pct": 10.0, "overall_win_pct": 55, "breakdown": []}
    cgd_intel.calc_custom_winrate = fake_calc
    try:
        c = _seed()
        d = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d["custom_calc"] == {"my_discount_pct": 10.0, "overall_win_pct": 55, "breakdown": []}, d
        # job_detail ส่ง args ถูก: district จาก intel_ctx amphoe, my_price/selected จาก calc_params
        assert captured["district"] == "นาทม" and captured["my_price"] == "900000", captured
        assert captured["selected"] == ["หจก.A"], captured
        assert captured["attend"] == {"หจก.A": 0.7}, captured
        assert d["predicted_attendees"]["probs"] == {"หจก.A": 0.7}, d
        # ไม่ส่ง calc_params → ไม่เรียก calc, custom_calc None
        d2 = pv.job_detail(c, "69010000001")
        assert d2["custom_calc"] is None, d2
        # intel_context None → graceful, ไม่ throw
        cgd_intel.intel_context = lambda *a, **k: None
        d3 = pv.job_detail(c, "69010000001",
                          calc_params={"my_price": "900000", "selected_names": ["หจก.A"], "extra_names": []})
        assert d3["custom_calc"] is None, d3
    finally:
        cgd_intel.intel_context = orig_ctx
        cgd_intel.calc_custom_winrate = orig_calc
    print("OK job_detail_custom_calc")


test_job_detail_custom_calc()

# --- render_job_page: intel_lines text ตัดออก (ซ้ำกับตารางคู่แข่ง/โอกาสชนะ — กัญจน์ 2026-06-28) ---
c = _seed()
d = pv.job_detail(c, "69010000001")
d["intel_lines"] = ["💡 ราคาอ้างอิง ทดสอบ", "🏆 คู่แข่งหลัก ทดสอบ"]
h = pv.render_job_page(d, "TOK", 0)
assert "📊 วิเคราะห์ราคา & คู่แข่งในพื้นที่" not in h, "intel text block ต้องถูกตัด (ซ้ำตาราง)"
assert "💡 ราคาอ้างอิง ทดสอบ" not in h, "ข้อความ intel ต้องไม่ render แล้ว (ใช้ตารางแทน)"
print("OK render_job_page_no_intel_text")

# --- render_job_page: company_tables (N+161 full company list, tin link / notin grey) ---
data_ct = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 0,
                   "deadline": None, "pred_lo": None, "pred_hi": None},
           "bidders": [], "intel_lines": ["💡 ราคาอ้างอิง (งานถนน ต.โพนทอง)"],
           "company_tables": [{"label": "🏘 ในตำบลโพนทอง", "n": 5, "conf_tag": "🟢", "p25": 10.0, "p75": 20.0,
                               "companies": [
                                   {"name": "หจก.A", "tin": "111", "games": 3, "median": 12.0,
                                    "p25": 10.0, "p75": 15.0, "project_ids": ["R1", "R2"]},
                                   {"name": "หจก.ไม่มีtin", "tin": None, "games": 1, "median": None,
                                    "p25": None, "p75": None, "project_ids": ["R3"]}]}],
           "winrate_table": None}
html_ct = pv.render_job_page(data_ct, "tok", 0)
assert "หจก.A" in html_ct and "หจก.ไม่มีtin" in html_ct, html_ct
assert "/portal/company?t=tok&tin=111" in html_ct, html_ct                  # tin resolve ได้ → ลิงก์
assert "area_ids=R1,R2" in html_ct, html_ct                                  # project_ids ติดไปด้วย
assert 'class="notin"' in html_ct, "ชื่อ resolve ไม่ได้ต้องเป็น grey ไม่คลิก"
print("OK render_job_page_company_table_with_tin_link")

# --- render_job_page: winrate_table (N+161 full N=1..max ladder, N=1 hardcoded 100%) ---
data_wt = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 0,
                   "deadline": None, "pred_lo": None, "pred_hi": None},
           "bidders": [], "intel_lines": [], "company_tables": [],
           "winrate_table": {"ns": [1, 2, 3, 4], "rows": [(1400000, [100, 78, 68, 59])],
                             "n_mean": 3.0, "n_sd": 1.0, "n_auctions": 10, "n_bids": 30,
                             "ess": 12.0, "k_mid": 3, "budget": 2000000, "conf": None, "price_basis": "ตำบล"}}
html_wt = pv.render_job_page(data_wt, "tok", 0)
assert "1 ราย" in html_wt and "4 ราย" in html_wt, html_wt    # ladder เต็ม N=1..4 (ไม่ใช่ 3 จุดเดิม)
assert "100%" in html_wt, html_wt                            # N=1 = 100% เสมอ
# N+166.1: กัญจน์ขอกลับเป็นตารางจริงกล่องเดียวมีเส้นกรอบ (เลิก card-transform ที่แยกเป็นหลายกล่อง)
assert 'class="itbl"' in html_wt, html_wt
assert "<table" in html_wt and html_wt.count("<table") == html_wt.count("</table>"), html_wt
print("OK render_job_page_winrate_table_full_ladder")

# --- render_job_page: custom winrate calculator form + result (N+168) ---
data_calc = {"job": {"project_id": "P1", "name": "งานทดสอบ", "location": "", "budget": 1000000,
                     "deadline": None, "pred_lo": None, "pred_hi": None},
            "bidders": [], "intel_lines": [],
            "company_tables": [{"label": "🏘 ในตำบลโพนทอง", "n": 5, "conf_tag": "🟢 มั่นใจ",
                                "p25": 10.0, "p75": 20.0, "median": 15.0,
                                "companies": [{"name": "หจก.A", "tin": "111", "games": 5,
                                              "median": 14.0, "p25": 10.0, "p75": 18.0,
                                              "project_ids": ["R1"]}]}],
            "winrate_table": None, "custom_calc": None}
html_form = pv.render_job_page(data_calc, "tok", 0)
assert 'name="my_price"' in html_form, html_form
assert 'value="หจก.A"' in html_form and "ชนะ 5 งาน" in html_form, html_form   # checkbox มาจาก company_tables
assert 'name="extra_names"' in html_form, html_form                          # textarea เพิ่มชื่ออื่น
assert "คำนวณโอกาสชนะ" in html_form, html_form

data_calc["custom_calc"] = {"my_discount_pct": 15.0, "overall_win_pct": 62,
                            "breakdown": [{"name": "หจก.A", "win_pct_against": 30,
                                           "source": "ตรงงาน+หน่วยงาน 12 ครั้ง", "has_history": True}]}
html_result = pv.render_job_page(data_calc, "tok", 0)
assert "โอกาสชนะของคุณรวม: 62%" in html_result, html_result
assert "หจก.A" in html_result and "ชนะคุณ ~30%" in html_result, html_result
assert "ตรงงาน+หน่วยงาน 12 ครั้ง" in html_result, html_result          # ป้าย source ต่อราย
assert "โมเดล Gates" in html_result, html_result                       # disclaimer ใหม่
print("OK render_job_page_custom_calc_form")

# --- area_portfolio + render_company_page area section (N+161 highlight area-of-origin jobs) ---
def _area_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE cgd_winners (project_id TEXT PRIMARY KEY, project_name TEXT,
        winner TEXT, win_price INTEGER, budget INTEGER)""")
    c.executemany("INSERT INTO cgd_winners VALUES (?,?,?,?,?)", [
        ("R1", "ถนน ต.โพนทอง", "หจก.A", 900000, 1000000),
        ("R2", "ถนน ต.โพนทอง", "หจก.A", 850000, 1000000),
        ("R3", "ถนน อ.อื่น", "หจก.A", 700000, 1000000),     # นอก area_ids → ไม่ติด
        ("R4", "ถนน ต.โพนทอง", "หจก.B", 600000, 1000000)])  # คนละบริษัท → ไม่ติด
    c.commit()
    return c


def test_area_portfolio_exact_match_only():
    c = _area_conn()
    # R3 ไม่ส่งมาใน id list เลย (อยู่นอก scope query ที่สร้าง ids ชุดนี้) — R4 ส่งมาแต่ winner คนละบริษัท → ตัด
    out = pv.area_portfolio(c, "หจก.A", ["R1", "R2", "R4"])
    assert out is not None and len(out["jobs"]) == 2, out
    ids = {j["project_id"] for j in out["jobs"]}
    assert ids == {"R1", "R2"}, ids
    assert pv.area_portfolio(c, "หจก.A", []) is None, "ว่าง → None"
    assert pv.area_portfolio(c, "หจก.ไม่มี", ["R1"]) is None, "ไม่เจอ → None"
    print("OK area_portfolio_exact_match_only")


def test_render_company_page_area_section_above_timeline():
    data = {"name": "หจก.A", "tin": "111", "is_sme": False, "total_bids": 2, "wins": 2,
            "win_rate": 100.0, "provinces": ["นครพนม"],
            "discount_hist": [{"lo": 0, "hi": 5, "count": 0}],
            "discount_avg": 12.0, "by_year": [{"year": 2568, "bids": 2, "wins": 2, "jobs": []}]}
    area = {"label_count": 2, "jobs": [{"project_id": "R1", "name": "ถนน ต.โพนทอง",
                                        "price": 900000, "discount": 10.0, "is_winner": True}]}
    html = pv.render_company_page(data, "tok", "", 0, area=area, area_label="🏘 ในตำบลโพนทอง")
    assert "📍 ผลงานในพื้นที่นี้" in html, html
    pos_area = html.index("📍 ผลงานในพื้นที่นี้")
    pos_timeline = html.index('class="yhead"')   # timeline แยกรายปี (ไม่ใช่ "ปี 2568" ที่ขึ้นก่อนใน chart 1 แล้ว)
    assert pos_area < pos_timeline, "area section ต้องอยู่ก่อน timeline แยกรายปี"
    print("OK render_company_page_area_section_above_timeline")


test_area_portfolio_exact_match_only()
test_render_company_page_area_section_above_timeline()


# --- _render_custom_calc_form: auto-predict (N+196) ---
def test_render_calc_form_auto_predict():
    ct = [{"label": "x", "companies": [
        {"name": "หจก.เอ", "games": 3, "median": 12.0},
        {"name": "หจก.บี", "games": 2, "median": 8.0}]}]
    pred = {"probs": {"หจก.เอ": 0.8}, "conf": None, "n_auctions": 8}
    # GET แรก (prefill=None) → กลุ่มทำนาย pre-tick, กลุ่มรองไม่ tick
    h = pv._render_custom_calc_form(ct, None, None, "TOK", "P1", pred)
    assert "ระบบเดาคู่แข่งให้" in h, h
    assert "โอกาสมา ~80%" in h, h
    assert 'value="หจก.เอ" checked' in h, h
    assert 'value="หจก.บี" checked' not in h and 'value="หจก.บี"' in h, h
    assert "เจ้าอื่นในพื้นที่" in h, h
    # หลัง submit ติ๊กออกหมด → ไม่ re-tick
    h2 = pv._render_custom_calc_form(ct, None, {"my_price": "900000", "selected_names": [],
                                                "extra_names": []}, "TOK", "P1", pred)
    assert 'value="หจก.เอ" checked' not in h2, h2
    # ทำนายไม่ได้ → header เดิม + note fallback
    h3 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1", None)
    assert "ระบบเดารายชื่อไม่ได้" in h3 and "คำนวณโอกาสชนะเจาะจงคู่แข่ง" in h3, h3
    assert "checked" not in h3, h3
    # conf 🟡 → ป้ายบอก scope
    h4 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1",
                                     {"probs": {"หจก.เอ": 0.8}, "conf": ("🟡", "อำเภอ"), "n_auctions": 6})
    assert "🟡 คำทำนายอิงข้อมูลอำเภอ" in h4, h4
    # ทำนายชื่อที่ไม่อยู่ใน company_tables (มาจาก bid_results ผู้แพ้) → render ได้ ไม่พัง
    h5 = pv._render_custom_calc_form(ct, None, None, "TOK", "P1",
                                     {"probs": {"หจก.นอกลิสต์": 0.6}, "conf": None, "n_auctions": 8})
    assert 'value="หจก.นอกลิสต์" checked' in h5, h5
    # breakdown แสดง "โอกาสมา X% · ถ้ามา ชนะคุณ ~Y%" / ไม่มี attend → conditional อย่างเดียว
    cc = {"overall_win_pct": 62, "my_discount_pct": 12.0, "breakdown": [
        {"name": "หจก.เอ", "win_pct_against": 55, "attend_pct": 80, "source": "", "has_history": True},
        {"name": "หจก.ซี", "win_pct_against": 30, "attend_pct": None, "source": "สนามทั่วไป", "has_history": False}]}
    h6 = pv._render_custom_calc_form(ct, cc, {"my_price": "880000", "selected_names": ["หจก.เอ"],
                                              "extra_names": ["หจก.ซี"]}, "TOK", "P1", pred)
    assert "โอกาสชนะของคุณรวม: 62%" in h6, h6
    assert "โอกาสมา 80% · ถ้ามา ชนะคุณ ~55%" in h6, h6
    assert "ถ้ามา ชนะคุณ ~30%" in h6 and "โอกาสมา 80% · ถ้ามา ชนะคุณ ~30%" not in h6, h6
    print("OK render_calc_form_auto_predict")

test_render_calc_form_auto_predict()

print("OK test_portal_views")
