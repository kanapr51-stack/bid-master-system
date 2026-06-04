"""Phase 3: ดึงทุก contract (มีผู้ชนะ 100%) นครพนม+บึงกาฬ ปี 2566-2568 (ไม่กรอง keyword)
→ เก็บดิบใน SQLite data/winner_history.db (table winner_history) + raw_json เผื่อ re-extract.
adaptive winner extraction (column-shift L-006) + price validate flag. checkpointable (resume ได้).

Usage:
  python scripts/_winner_history_build.py            # fetch + store (resume)
  python scripts/_winner_history_build.py --stats    # สรุปจาก DB อย่างเดียว
"""
import sys, os, json, sqlite3, time, argparse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
import cgd_api_client as cg

DB = "data/winner_history.db"
CKPT = "data/_wh_fetch_ckpt.json"
PROVS = ["นครพนม", "บึงกาฬ"]
PAGE = 1000
CALL_BUDGET = 700          # quota 1000/วัน, ใช้ไปบ้างแล้ว → buffer

MARKERS = ("บริษัท", "ห้างหุ้นส่วน", "หจก", "ห้าง", "นาย ", "นาง", "น.ส.", "ร้าน",
           "กิจการร่วมค้า", "สหกรณ์", "วิสาหกิจ", "คณะบุคคล", "องค์การ")
SKIP_FIELDS = {"ชื่อโครงการ", "ชื่อหน่วยงาน", "ชื่อหน่วยงานย่อย", "ชื่อประเภทโครงการ",
               "วิธีจัดซื้อฯ", "กลุ่มวิธีจัดซื้อฯ"}


def _f(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _s(x):
    """coerce ทุก type → str ปลอดภัย (column-shift ทำให้บาง field เป็น float/None)"""
    return "" if x is None else str(x).strip()


def cgd_winner(r):
    """หา winner แบบ adaptive: field แรกที่มี marker บริษัท ยกเว้นชื่องาน/หน่วยงาน"""
    for k, v in r.items():
        if k in SKIP_FIELDS:
            continue
        s = str(v)
        if any(m in s for m in MARKERS):
            return s.strip()
    return ""


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS winner_history (
            project_id    TEXT PRIMARY KEY,
            fiscal_year   TEXT,
            province      TEXT,
            district      TEXT,
            subdistrict   TEXT,
            project_name  TEXT,
            dept          TEXT,
            proc_type     TEXT,
            winner        TEXT,
            winner_tin    TEXT,
            budget        INTEGER,
            mid_price     INTEGER,
            win_price     INTEGER,
            discount_pct  REAL,
            price_valid   INTEGER,
            announce_date TEXT,
            contract_no   TEXT,
            sign_date     TEXT,
            status        TEXT,
            source        TEXT,
            raw_json      TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_prov ON winner_history(province)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_fy ON winner_history(fiscal_year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wh_winner ON winner_history(winner)")
    conn.commit()
    return conn


def row_from_rec(r, yr):
    win_name = cgd_winner(r)
    mid = _f(r.get("ราคากลาง(บาท)"))
    win = _f(r.get("ราคาตกลงซื้อ/จ้าง"))
    valid = 1 if (win > 0 and mid > 0 and win <= mid * 1.5) else 0
    disc = round((mid - win) / mid * 100, 2) if (valid and mid > 0) else None
    return (
        _s(r.get("รหัสโครงการ")),
        _s(r.get("ปีงบประมาณ")) or yr,
        _s(r.get("จังหวัด")),
        _s(r.get("เขต/อำเภอ")),
        _s(r.get("แขวง/ตำบล")),
        _s(r.get("ชื่อโครงการ")),
        _s(r.get("ชื่อหน่วยงาน")),
        _s(r.get("วิธีจัดซื้อฯ")),
        win_name,
        _s(r.get("เลขนิติบุคคล")),
        int(_f(r.get("งบประมาณ(บาท)"))),
        int(mid), int(win), disc, valid,
        _s(r.get("วันที่ประกาศ")),
        _s(r.get("เลขที่สัญญา")),
        _s(r.get("วันที่ลงนามสัญญา")),
        _s(r.get("สถานะโครงการ")),
        "CGD",
        json.dumps(r, ensure_ascii=False),
    )


COLS = ("project_id,fiscal_year,province,district,subdistrict,project_name,dept,proc_type,"
        "winner,winner_tin,budget,mid_price,win_price,discount_pct,price_valid,"
        "announce_date,contract_no,sign_date,status,source,raw_json")
PH = ",".join("?" * 21)


def load_ckpt():
    if os.path.exists(CKPT):
        return set(json.load(open(CKPT, encoding="utf-8")))
    return set()


def save_ckpt(done):
    json.dump(sorted(done), open(CKPT, "w", encoding="utf-8"), ensure_ascii=False)


def fetch_all():
    rids = json.load(open("data/_cgd_rids_67_66.json", encoding="utf-8"))
    rids["2568"] = cg.EGP_CONTRACT_2568_RIDS
    conn = init_db()
    done = load_ckpt()
    calls = 0
    for yr in ["2568", "2567", "2566"]:
        for prov in PROVS:
            for ri, rid in enumerate(rids[yr]):
                key = f"{yr}|{prov}|{rid}"
                if key in done:
                    continue
                offset = 0
                n = 0
                while calls < CALL_BUDGET:
                    res = cg._datastore_search(rid, filters={"จังหวัด": prov}, limit=PAGE, offset=offset)
                    calls += 1
                    if not res or not res.get("records"):
                        break
                    recs = res["records"]
                    total = res.get("total", 0)
                    batch = [row_from_rec(r, yr) for r in recs if str(r.get("รหัสโครงการ") or "").strip()]
                    conn.executemany(f"INSERT OR IGNORE INTO winner_history ({COLS}) VALUES ({PH})", batch)
                    conn.commit()
                    n += len(batch)
                    offset += PAGE
                    if offset >= total:
                        break
                if calls >= CALL_BUDGET:
                    print(f"⚠️ ชน CALL_BUDGET {CALL_BUDGET} — checkpoint+หยุด (รันใหม่เพื่อ resume)")
                    save_ckpt(done)
                    _print_stats(conn)
                    return
                done.add(key)
                save_ckpt(done)
                print(f"{yr} {prov} file{ri+1}: +{n} | calls={calls} | total in DB={conn.execute('SELECT COUNT(*) FROM winner_history').fetchone()[0]:,}")
    print(f"\n✅ เสร็จครบ | total calls: {calls}")
    _print_stats(conn)


def _print_stats(conn):
    c = conn.cursor()
    tot = c.execute("SELECT COUNT(*) FROM winner_history").fetchone()[0]
    print(f"\n=== winner_history stats ===\nรวม: {tot:,}")
    print("แยกปี×จังหวัด:")
    for row in c.execute("SELECT fiscal_year, province, COUNT(*) FROM winner_history GROUP BY fiscal_year, province ORDER BY fiscal_year DESC, province"):
        print(f"  {row[0]} {row[1]}: {row[2]:,}")
    pv = c.execute("SELECT SUM(price_valid), COUNT(*) FROM winner_history").fetchone()
    print(f"price_valid: {pv[0]:,}/{pv[1]:,} ({pv[0]/max(pv[1],1)*100:.1f}%)")
    wn = c.execute("SELECT COUNT(*) FROM winner_history WHERE winner != ''").fetchone()[0]
    print(f"มีชื่อผู้ชนะ (adaptive): {wn:,}/{tot:,} ({wn/max(tot,1)*100:.1f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        _print_stats(init_db())
    else:
        fetch_all()
