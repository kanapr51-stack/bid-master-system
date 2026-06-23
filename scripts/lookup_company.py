"""lookup_company.py — โปรไฟล์คู่แข่งเชิงลึก จากประวัติชนะประมูลทั้งประเทศ 11 ปี (2558-2568).

ดึงจาก CGD open-data API (data.go.th) ด้วย q-sweep ทุก resource ทุกปี → ไม่ต้อง sync ทั้งจังหวัด
(~96 calls/บริษัท). จัดการ column-shift ของ CGD โดยอ่านเฉพาะฟิลด์ก่อนจุดเลื่อน + จำแนกวิธี/หมวดจาก
ชื่องาน (เชื่อถือได้กว่าคอลัมน์วิธีที่เลื่อน). สถิติเป็น pure function (compute_profile) เทสต์แยกได้.

ใช้:  python scripts/lookup_company.py "ห้างหุ้นส่วนจำกัด หนองหว้า การก่อสร้าง"
"""
import sys, os, json, time, statistics as st
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))

_LEGAL_PREFIX = ("ห้างหุ้นส่วนจำกัด", "ห้างหุ้นส่วนสามัญ", "บริษัท", "หจก.", "หจก",
                 "บจก.", "บจก", "ห้าง")
DISC_MAX = 60.0          # ลด > นี้ หรือ < 0 = column-shift/บั๊กข้อมูล CGD → ตัดออกจากสถิติ %ลด
RID_FILES = ["data/_cgd_rids_67_66.json", "data/_cgd_rids_58_65.json"]


def _q_term(name: str) -> str:
    """ตัด prefix นิติบุคคลนำหน้า → เหลือชื่อเด่นไว้ q-search (CKAN full-text)."""
    s = (name or "").strip()
    for p in _LEGAL_PREFIX:
        if s.startswith(p):
            return s[len(p):].lstrip(" .").strip()
    return s


def _method(project_name: str) -> str:
    """วิธีจัดซื้อจากชื่องาน (เชื่อกว่าคอลัมน์ที่เลื่อน): competitive=ประกวดราคา · direct=เฉพาะเจาะจง."""
    n = project_name or ""
    if n.lstrip().startswith("ประกวดราคา"):
        return "competitive"
    if "เฉพาะเจาะจง" in n or "โดยวิธีเฉพาะ" in n:
        return "direct"
    return "other"


def _category(project_name: str) -> str:
    """หมวดงานหยาบจาก keyword ในชื่องาน."""
    n = project_name or ""
    if "ถนน" in n or "ทางหลวง" in n:
        return "ถนน"
    if "น้ำเสีย" in n or "ประปา" in n or "บำบัดน้ำ" in n or "น้ำ" in n:
        return "น้ำ"
    if "อาคาร" in n or "ซ่อมแซม" in n or "ปรับปรุง" in n or "ห้อง" in n or "โรงเรียน" in n:
        return "อาคาร"
    return "อื่นๆ"


def _num(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_profile(jobs: list) -> dict:
    """สถิติเชิงลึกจาก jobs=[{pid,yr,prov,budget,agree,name,dept}] (pure). %ลด ตัด bad row (disc<0/>60)."""
    n = len(jobs)
    base = {"total_wins": n, "total_value": 0.0, "year_min": None, "year_max": None,
            "by_year": {}, "by_province": {}, "home_province": None, "by_method": {},
            "by_category": {}, "competitive_disc": {"n": 0}, "direct_disc": {"n": 0},
            "budget": {}, "bad_rows": 0, "jobs": jobs}
    if n == 0:
        return base
    base["total_value"] = sum(_num(j["agree"]) for j in jobs)
    yrs = [str(j["yr"]) for j in jobs if j.get("yr")]
    base["year_min"], base["year_max"] = (min(yrs), max(yrs)) if yrs else (None, None)
    by_year = defaultdict(lambda: {"n": 0, "value": 0.0})
    for j in jobs:
        y = str(j.get("yr") or "?")
        by_year[y]["n"] += 1
        by_year[y]["value"] += _num(j["agree"])
    base["by_year"] = {y: by_year[y] for y in sorted(by_year)}
    prov = Counter(j.get("prov") or "?" for j in jobs)
    base["by_province"] = dict(prov.most_common())
    base["home_province"] = prov.most_common(1)[0][0]
    base["by_method"] = dict(Counter(_method(j["name"]) for j in jobs))
    base["by_category"] = dict(Counter(_category(j["name"]) for j in jobs))
    comp, direct, bad = [], [], 0
    for j in jobs:
        b, a = _num(j["budget"]), _num(j["agree"])
        if b <= 0 or a <= 0:
            continue
        disc = (b - a) / b * 100.0
        if disc < 0 or disc > DISC_MAX:
            bad += 1
            continue
        (comp if _method(j["name"]) == "competitive" else direct).append(disc)
    base["bad_rows"] = bad

    def _stat(xs):
        return {"n": len(xs), "median": round(st.median(xs), 1), "min": round(min(xs), 1),
                "max": round(max(xs), 1)} if xs else {"n": 0}
    base["competitive_disc"], base["direct_disc"] = _stat(comp), _stat(direct)
    buds = [_num(j["budget"]) for j in jobs if _num(j["budget"]) > 0]
    if buds:
        base["budget"] = {"min": int(min(buds)), "median": int(st.median(buds)), "max": int(max(buds))}
    return base


# ---- API fetch (ไม่ pure — แยกจาก compute_profile เพื่อให้สถิติเทสต์ได้) -------------------
def _load_all_rids() -> dict:
    import cgd_api_client as cc
    rids = {"2568": list(getattr(cc, "EGP_CONTRACT_2568_RIDS", []))}
    for f in RID_FILES:
        if os.path.exists(f):
            rids.update(json.load(open(f, encoding="utf-8")))
    return rids


def _extract(rec: dict) -> dict:
    """ดึงฟิลด์ 'ก่อนจุดเลื่อน' (เชื่อถือได้แม้ column-shift) จาก record CGD ดิบ."""
    return {"pid": str(rec.get("รหัสโครงการ") or ""), "yr": str(rec.get("ปีงบประมาณ") or ""),
            "prov": rec.get("จังหวัด") or "", "name": str(rec.get("ชื่อโครงการ") or ""),
            "dept": str(rec.get("ชื่อหน่วยงาน") or ""), "budget": rec.get("งบประมาณ(บาท)"),
            "agree": rec.get("ราคาตกลงซื้อ/จ้าง")}


def fetch_company_rows(name: str, log=print) -> tuple:
    """q-sweep ทุก RID → records ที่ normalized ตรงชื่อบริษัท (dedupe by project_id). คืน (jobs, calls)."""
    import cgd_api_client as cc
    import portal_views as pv
    cc.get_token()
    target = pv._norm_name(name)
    q = _q_term(name)
    rids = _load_all_rids()
    seen, calls, skipped = {}, 0, 0
    for yr in sorted(rids, reverse=True):
        for rid in rids[yr]:
            try:
                res = cc._datastore_search(rid, q=q, limit=200)
                calls += 1
            except Exception as e:
                log(f"  err {yr} {type(e).__name__}")
                skipped += 1
                continue
            if not res:                      # None = HTTP error/quota (429) → ข้าม (อย่าพัง)
                skipped += 1
                continue
            for r in (res.get("records") or []):
                if any(pv._norm_name(str(v)) == target for v in r.values()):
                    j = _extract(r)
                    if j["pid"] and j["pid"] not in seen:
                        seen[j["pid"]] = j
            time.sleep(0.3)
    return list(seen.values()), calls, skipped


def format_report(name: str, profile: dict, calls: int = 0) -> str:
    p = profile
    out = [f"🏢 {name}", "=" * 56]
    if p["total_wins"] == 0:
        out.append("ไม่พบประวัติชนะประมูลในข้อมูล CGD (2558-2568)")
        return "\n".join(out)
    out.append(f"ชนะรวม {p['total_wins']} งาน · มูลค่ารวม {p['total_value']:,.0f} บาท "
               f"· ปี {p['year_min']}-{p['year_max']}")
    out.append(f"🏠 ฐานหลัก: {p['home_province']} "
               + " · ".join(f"{k} {v}" for k, v in list(p['by_province'].items())[:6]))
    bm = p["by_method"]
    out.append(f"วิธี: ประกวดราคา {bm.get('competitive',0)} · เฉพาะเจาะจง {bm.get('direct',0)} "
               f"· อื่นๆ {bm.get('other',0)}")
    out.append("หมวดงาน: " + " · ".join(f"{k} {v}" for k, v in
               sorted(p["by_category"].items(), key=lambda x: -x[1])))
    cd = p["competitive_disc"]
    if cd["n"]:
        out.append(f"💸 ลดราคา (e-bidding แข่งจริง, n={cd['n']}): median {cd['median']}% "
                   f"(ช่วง {cd['min']}-{cd['max']}%)")
    if p["direct_disc"]["n"]:
        out.append(f"   เฉพาะเจาะจง (n={p['direct_disc']['n']}): median {p['direct_disc']['median']}%")
    if p["budget"]:
        b = p["budget"]
        out.append(f"ขนาดงาน: {b['min']:,}–{b['max']:,} บาท (median {b['median']:,})")
    out.append("📈 ต่อปี: " + " · ".join(f"{y}:{d['n']}" for y, d in p["by_year"].items()))
    if p["bad_rows"]:
        out.append(f"⚠️ ตัด {p['bad_rows']} งานข้อมูลเพี้ยน (ราคาตกลง>งบ — column-shift CGD ปีเก่า)")
    out.append("-" * 56)
    for j in sorted(p["jobs"], key=lambda x: str(x["yr"])):
        b, a = _num(j["budget"]), _num(j["agree"])
        disc = f"{(b-a)/b*100:.1f}%" if b > 0 and 0 <= (b-a)/b*100 <= DISC_MAX else "—"
        out.append(f" {j['yr']} {j['prov']:<12} งบ{b:>12,.0f} ลด{disc:>6} | {j['name'][:34]}")
    if calls:
        out.append(f"\n({calls} API calls)")
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print('ใช้: python scripts/lookup_company.py "ชื่อบริษัท"'); return
    name = sys.argv[1]
    print(f"กำลังค้น {name} ... (q-sweep ~96 resources)")
    jobs, calls, skipped = fetch_company_rows(name)
    if not jobs and skipped > calls // 2:        # ส่วนใหญ่โดน 429 → quota หมด ไม่ใช่ "ไม่มีประวัติ"
        print(f"⚠️ CGD quota หมด/rate-limit ({skipped}/{calls+skipped} calls โดน 429) — "
              f"ลองใหม่พรุ่งนี้ หรือ register OPEND token เพิ่ม")
        return
    if skipped:
        print(f"⚠️ {skipped} resources ข้าม (rate-limit) — ผลอาจไม่ครบทุกปี")
    print(format_report(name, compute_profile(jobs), calls))


if __name__ == "__main__":
    main()
