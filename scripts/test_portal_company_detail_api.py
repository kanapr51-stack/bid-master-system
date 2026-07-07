"""test_portal_company_detail_api.py — JSON endpoint หน้าบริษัทธีม Board B
(GET /api/portal/company-detail) + href บริษัทใน job-detail เป็น relative ธีม B."""
import os, sys, json, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t", BMS_FOLLOW_SECRET="fs")
sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Customer_DB as db; db.init_schema()
import bms_api
import portal_views
from fastapi import HTTPException

PID = "69000000001"       # งานที่เจอกัน (h2h)
PID2 = "69000000002"      # งานที่คู่แข่งยื่นคนเดียว
TIN_THEM = "0403000000001"
TIN_US = "0403000000009"
NAME_THEM = "หจก.ผู้ชนะ"


def seed():
    norm = portal_views._norm_name(NAME_THEM)
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, company_tin, created_at, updated_at) "
                     "VALUES ('U1','ทดสอบ','trial',?, '2026-01-01','2026-01-01')", (TIN_US,))
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                     "VALUES ('U2','ไม่มีบริษัท','trial','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES (?, 'D0', 'นครพนม', 5000000, 'จ้างก่อสร้างถนน คสล. ทดสอบ', '2026-07-01')", (PID,))
        conn.execute("INSERT INTO projects_seen (project_id, announce_type, province, budget, project_name, first_seen_at) "
                     "VALUES (?, 'D0', 'นครพนม', 3000000, 'จ้างซ่อมถนนลูกรัง ทดสอบ', '2026-07-02')", (PID2,))
        # P1: เจอกัน — เขาชนะ
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner) "
                     "VALUES (?, ?, ?, '4500000', '4500000', 1)", (PID, NAME_THEM, TIN_THEM))
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner) "
                     "VALUES (?, 'หจก.เรา', ?, '4600000', NULL, 0)", (PID, TIN_US))
        # P2: เขายื่นคนเดียว ไม่ชนะ → profile: ยื่น 2 ชนะ 1 (win_rate 50%)
        conn.execute("INSERT INTO bid_results (project_id, bidder_name, bidder_tin, price_proposal, price_agree, is_winner) "
                     "VALUES (?, ?, ?, '2900000', NULL, 0)", (PID2, NAME_THEM, TIN_THEM))
        # cgd_winners: 1 ประมูล + 1 เจาะจง (join ด้วย normalized_winner ไม่ใช่ tin — N+157)
        conn.execute("INSERT INTO cgd_winners (project_id, province, project_name, winner, normalized_winner, "
                     "budget, win_price, proc_type) VALUES ('CG1','นครพนม','ก่อสร้างถนน คสล. สาย 1',?,?,"
                     "5000000,4500000,'ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)')", (NAME_THEM, norm))
        conn.execute("INSERT INTO cgd_winners (project_id, province, project_name, winner, normalized_winner, "
                     "budget, win_price, proc_type) VALUES ('CG2','นครพนม','ซื้อวัสดุก่อสร้าง',?,?,"
                     "400000,400000,'เฉพาะเจาะจง')", (NAME_THEM, norm))


async def main():
    seed()
    # 403 เมื่อ secret ผิด
    try:
        await bms_api.portal_company_detail_json(line_user_id='U1', tin=TIN_THEM, x_bms_secret='bad')
        assert False, "expected 403"
    except HTTPException as e:
        assert e.status_code == 403

    # ไม่พบบริษัท
    r = await bms_api.portal_company_detail_json(line_user_id='U1', tin='0000000000000', x_bms_secret='t')
    assert r == {"ok": False, "error": "not_found"}, r

    # โครงเต็ม: profile + h2h + won + serialize ได้
    r = await bms_api.portal_company_detail_json(line_user_id='U1', tin=TIN_THEM, x_bms_secret='t')
    assert r["ok"], r
    d = r["data"]
    p = d["profile"]
    assert p["name"] == NAME_THEM and p["tin"] == TIN_THEM, p
    assert p["total_bids"] == 2 and p["wins"] == 1 and p["win_rate"] == 50.0, p
    assert d["h2h"] and d["h2h"]["shared"] == 1 and d["h2h"]["their_wins"] == 1 \
        and d["h2h"]["our_wins"] == 0 and d["h2h"]["our_name"] == "หจก.เรา", d["h2h"]
    w = d["won"]
    assert w and w["total"]["count"] == 2 and w["groups"]["bid"]["count"] == 1 \
        and w["groups"]["specific"]["count"] == 1 and w["proc"] == "all" and len(w["jobs"]) == 2, w
    assert d["area"] is None and d["area_label"] == "", d
    json.dumps(d, ensure_ascii=False)  # ต้อง serialize ได้ทั้งก้อน

    # proc filter: stats เต็ม, job list กรองเหลือประมูลอย่างเดียว
    r = await bms_api.portal_company_detail_json(line_user_id='U1', tin=TIN_THEM, proc='bid', x_bms_secret='t')
    w = r["data"]["won"]
    assert w["proc"] == "bid" and len(w["jobs"]) == 1 and w["jobs"][0]["pid"] == "CG1", w
    assert w["total"]["count"] == 2, w  # stats ไม่ถูกกรอง

    # area scope: กรองเฉพาะ project_ids ที่ส่งมา + คืน label กลับ
    r = await bms_api.portal_company_detail_json(line_user_id='U1', tin=TIN_THEM,
                                                 area_ids='CG1, CGX', area_label='ต.ทดสอบ', x_bms_secret='t')
    a = r["data"]["area"]
    assert a and a["label_count"] == 1 and a["jobs"][0]["project_id"] == "CG1", a
    assert r["data"]["area_label"] == "ต.ทดสอบ", r["data"]["area_label"]

    # ลูกค้าไม่มี company_tin → h2h = None (ไม่ crash)
    r = await bms_api.portal_company_detail_json(line_user_id='U2', tin=TIN_THEM, x_bms_secret='t')
    assert r["ok"] and r["data"]["h2h"] is None, r["data"]["h2h"]

    # href บริษัทใน job-detail ต้องเป็น relative ธีม B แล้ว (N+188)
    r = await bms_api.portal_job_detail_json(line_user_id='U1', pid=PID, x_bms_secret='t')
    hrefs = [b["href"] for b in r["data"]["bidders"] if b.get("href")]
    assert hrefs and all(h.startswith("/portal/company/") for h in hrefs), hrefs
    assert f"/portal/company/{TIN_THEM}?from={PID}" in hrefs, hrefs

    print("PASS test_portal_company_detail_api")


asyncio.run(main())
