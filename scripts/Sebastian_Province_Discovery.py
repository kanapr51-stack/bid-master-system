"""
Sebastian_Province_Discovery.py — Province-based D0 discovery via eGP announcement search API

ค้นพบ 2026-05-30: endpoint ค้นหาประกาศตามจังหวัด (moiId) เห็นหน่วยงานท้องถิ่น
(อบต./เทศบาล/รพ.สต./โรงเรียน) ที่ RSS มองไม่เห็นเลย

Flow:
  [token harvest ผ่าน Cloudflare Turnstile — ดู memory/project_province_search_api.md]
    → X-Announcement-Token (portable bearer 30 นาที)
  GET announcement?budgetYear=2569&moiId=X&announceType=2&page=N  (announceType=2 = D0)
    → dedupe vs projects_seen → insert (source='province_api', province รู้แน่นอน)
    → notifier เดิม match subscription → queue → enrichment → LINE

Token (เลือกอย่างใดอย่างหนึ่ง):
  --token <value>                      หรือ
  env BMS_ANNOUNCEMENT_TOKEN

Usage:
  python Sebastian_Province_Discovery.py --token <T> --dry-run          # พิสูจน์ ไม่เขียน DB
  python Sebastian_Province_Discovery.py --token <T> --ingest           # เขียน projects_seen
  python Sebastian_Province_Discovery.py --token <T> --filter-amphoe    # กรองเฉพาะ อ.เป้าหมาย
"""

import sys
import os
import time
import json
import argparse
import sqlite3
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(encoding="utf-8")

API = "https://process5.gprocurement.go.th/egp-atpj27-service/pb/a-egp-allt-project/announcement"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://process5.gprocurement.go.th/egp-agpc01-web/announcement",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}

# moiId → ชื่อจังหวัด (ที่ตรงกับ subscription_provinces)
PROVINCE_MOI = {
    "480000": "นครพนม",
    "380000": "บึงกาฬ",
}

# อำเภอเป้าหมาย (pilot) — ดู memory/project_target_areas.md
TARGET_AMPHOE = {
    "นครพนม": ["บ้านแพง"],
    "บึงกาฬ": ["บึงโขงหลง"],
}

ANNOUNCE_TYPE_D0 = "2"   # numeric — 2 = D0 (ประกาศเชิญชวน)

TIMEOUT = 15
PAGE_SLEEP = 1.5         # เคารพ rate limit (~100 req / 120s)
COOLDOWN_EVERY = 50      # ทุก 50 req
COOLDOWN_SEC = 30        # พัก 30s (กัน throttle — bug บึงกาฬ 2026-05-30)
MAX_CONSEC_EMPTY = 3     # หน้าว่างติดกัน N → abort (กัน balloon จน systemd timeout — P1 2026-05-31)
INCR_KNOWN_STOP = 2      # incremental หยุดเมื่อเจอหน้าที่รู้หมด N หน้า "ติดกัน" (margin กัน ties/boundary)
RECONCILE_DAYS = 2       # full sweep: งานใหม่ announceDate เก่ากว่านี้ = incremental น่าจะพลาด → alert

_req_count = 0           # นับ req ข้ามทุกจังหวัด (rate limit เป็น global)


def _rate_limit_tick():
    """เรียกหลังทุก request — cooldown ทุก COOLDOWN_EVERY req"""
    global _req_count
    _req_count += 1
    if _req_count % COOLDOWN_EVERY == 0:
        print(f"    ⏳ cooldown {COOLDOWN_SEC}s (req #{_req_count} — กัน rate limit)")
        time.sleep(COOLDOWN_SEC)
    else:
        time.sleep(PAGE_SLEEP)


def _db_path() -> str:
    return os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"), "bms_customers.db")


def _all_known_ids() -> set:
    """project_id ทั้งหมดใน projects_seen (สำหรับ incremental stop / full reconcile — dedup global)"""
    conn = sqlite3.connect(_db_path())
    try:
        return {r[0] for r in conn.execute("SELECT project_id FROM projects_seen").fetchall()}
    finally:
        conn.close()


def _discord(msg: str) -> None:
    """ส่ง Discord (guarded — ไม่ให้ discovery ล้มถ้า Discord พัง)"""
    try:
        from Sebastian_Discord_Notify import load_env, get_credentials, send
        load_env()
        t, ch = get_credentials()
        send(t, ch, msg)
    except Exception:
        pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_heartbeat(status: str, **counts) -> None:
    """dead-man switch heartbeat — เขียนทุกครั้งที่ discovery รัน (P1 observability).
    status: 'ok' (ได้ข้อมูล) | 'no_data' (token reject/empty — ต้องสงสัย)"""
    try:
        hb = {"ts": _utc_now(), "status": status, **counts}
        path = os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"),
                            "last_discovery_run.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(hb, f, ensure_ascii=False)
    except Exception:
        pass


class RateLimited(Exception):
    """eGP ตอบ plain text 'Rate limit exceeded' — แยกจาก token reject"""


def _get(token: str, params: dict, path: str = "") -> dict | None:
    url = API + path
    hdrs = {**HEADERS, "X-Announcement-Token": token}
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=TIMEOUT)
        # rate limit = plain text ไม่ใช่ JSON → อย่าตีความเป็น token reject
        if "rate limit" in (r.text or "").lower():
            raise RateLimited()
        if not r.ok:
            return None
        return r.json()
    except RateLimited:
        raise
    except Exception:
        return None


def count_d0(token: str, moi_id: str, budget_year: str,
             announce_type: str = ANNOUNCE_TYPE_D0) -> tuple[int, int]:
    """คืน (recordsTotal, totalPages) จาก sumProjectMoneyAndCount
    announce_type: 2=D0(ประมูล, default) / 1=B0(รับฟังคำวิจารณ์)
    sentinel: (-1,-1)=token reject/error, (-2,-2)=rate limited"""
    try:
        body = _get(token, {
            "budgetYear": budget_year, "moiId": moi_id, "announceType": announce_type,
        }, path="/sumProjectMoneyAndCount")
    except RateLimited:
        return -2, -2
    if not body:
        return -1, -1
    d = body.get("data") or {}
    if d.get("recordsTotal") is None:
        return -1, -1   # token reject / validateCfTurnTile
    return int(d.get("recordsTotal") or 0), int(d.get("totalPages") or 0)


def fetch_page(token: str, moi_id: str, budget_year: str, page: int,
               announce_type: str = ANNOUNCE_TYPE_D0) -> list[dict]:
    # P1: ปล่อย RateLimited propagate (ไม่ swallow) → fetch_all_d0 abort ทันที กัน balloon
    body = _get(token, {
        "budgetYear": budget_year, "moiId": moi_id,
        "announceType": announce_type, "page": str(page),
    })
    if not body:
        return []
    data = body.get("data") or {}
    return data.get("data") or []


def fetch_all_d0(token: str, moi_id: str, budget_year: str,
                 known_ids: set | None = None,
                 announce_type: str = ANNOUNCE_TYPE_D0) -> list[dict]:
    """ดึงหน้าของจังหวัด (เรียง announceDate ใหม่→เก่า).
    announce_type: 2=D0(ประมูล, default) / 1=B0(รับฟังคำวิจารณ์)
    incremental (known_ids != None): หยุดเมื่อเจอหน้าที่ project_id รู้จักทั้งหมด
    (หน้าถัดไปเก่ากว่า = ingest แล้ว) → ลด req ~90% (P3 2026-05-31)"""
    province = PROVINCE_MOI.get(moi_id, moi_id)
    incremental = known_ids is not None
    total, pages = count_d0(token, moi_id, budget_year, announce_type)
    if total == -2:
        print(f"  ⚠️ {province}: rate limited — พัก {COOLDOWN_SEC}s แล้ว retry count")
        time.sleep(COOLDOWN_SEC)
        total, pages = count_d0(token, moi_id, budget_year, announce_type)
    if total == -2:
        # P1: abort ทันที (ไม่ return [] แล้วปล่อยจังหวัดถัดไปโดนซ้ำ) → main เขียน heartbeat+alert
        raise RateLimited(f"{province}: count rate-limited (ยังโดนหลัง retry)")
    if total < 0:
        print(f"  ❌ {province}: token reject (validateCfTurnTile) — token หมดอายุ/ผิด")
        return []
    mode_tag = " [incremental]" if incremental else ""
    print(f"  {province} (moiId={moi_id}): {total} โครงการ / {pages} หน้า{mode_tag}")
    out = []
    consec_empty = 0
    consec_known = 0
    for p in range(1, pages + 1):
        try:
            items = fetch_page(token, moi_id, budget_year, p, announce_type)
        except RateLimited:
            raise RateLimited(f"{province}: หน้า {p} rate-limited — abort (กัน balloon)")
        _rate_limit_tick()
        # empty แต่ยังไม่ถึงปลาย → อาจ silent throttle → retry ครั้งเดียว + circuit breaker
        if not items and len(out) < total:
            consec_empty += 1
            if consec_empty >= MAX_CONSEC_EMPTY:
                raise RateLimited(
                    f"{province}: หน้าว่างติดกัน {consec_empty} (silent throttle) — abort กัน balloon")
            print(f"    ⚠️ หน้า {p} ว่าง — พัก {COOLDOWN_SEC}s retry ({consec_empty}/{MAX_CONSEC_EMPTY})")
            time.sleep(COOLDOWN_SEC)
            try:
                items = fetch_page(token, moi_id, budget_year, p, announce_type)
            except RateLimited:
                raise RateLimited(f"{province}: หน้า {p} retry rate-limited — abort")
            _rate_limit_tick()
        if items:
            consec_empty = 0
        out.extend(items)
        # incremental: หยุดเมื่อเจอหน้าที่รู้หมด INCR_KNOWN_STOP หน้า "ติดกัน" (margin กัน ties)
        # นับเฉพาะงาน active(≠R) ที่ไม่รู้จัก — งานยกเลิกไม่เคย ingest จึงไม่อยู่ใน known (อย่านับเป็น new)
        if incremental and items:
            new_in_page = sum(
                1 for it in items
                if (it.get("projectStatus") or "") != "R"
                and str(it.get("projectId") or "") not in known_ids)
            if new_in_page == 0:
                consec_known += 1
                if consec_known >= INCR_KNOWN_STOP:
                    print(f"    ⏹ {province}: หน้า {p} (รู้หมด {consec_known} หน้าติดกัน) — หยุด "
                          f"(incremental, ข้าม {pages - p} หน้า)")
                    break
            else:
                consec_known = 0
        if p % 10 == 0 or p == pages:
            print(f"    หน้า {p}/{pages} — สะสม {len(out)} รายการ")
    return out


def normalize(item: dict, province: str) -> dict:
    return {
        "project_id":   str(item.get("projectId") or ""),
        "announce_type": item.get("announceType") or "D0",
        "province":     province,                       # รู้แน่นอนจาก moiId
        "budget":       int(item.get("projectMoney") or 0),
        "project_name": item.get("projectName") or "",
        "dept_name":    item.get("deptSubName") or "",
        "project_status": item.get("projectStatus") or "",   # A=active, R=cancelled
        "step_id":      item.get("stepId") or "",
        "announce_date": (item.get("announceDate") or "")[:10],
    }


def in_target_amphoe(rec: dict) -> bool:
    """match ชื่ออำเภอเป้าหมายใน project_name หรือ dept_name"""
    amphoes = TARGET_AMPHOE.get(rec["province"], [])
    hay = rec["project_name"] + " " + rec["dept_name"]
    return any(a in hay for a in amphoes)


def _stage_rank(announce_type: str) -> int:
    """ลำดับ lifecycle ตามอักษรแรก: B(รับฟัง)=0 < D(ประมูล)=1 < W(ผู้ชนะ)=2. อื่น=-1."""
    return {"B": 0, "D": 1, "W": 2}.get((announce_type or "")[:1], -1)


def ingest(records: list[dict]) -> tuple[int, int, int]:
    """upsert ลง projects_seen (source='province_api'), คืน (new, skipped, advanced).
    advance-stage: เจอ project เดิมที่ stage สูงขึ้น (B0→D0→W0) → update announce_type +
    stage_updated_at → projects_seen สะท้อน lifecycle ปัจจุบันจริง (ไม่ใช่แค่ stage แรกที่เห็น)."""
    conn = sqlite3.connect(_db_path())
    new = skipped = advanced = 0
    now = _utc_now()
    try:
        for r in records:
            if r["project_status"] == "R":   # ยกเลิก — ไม่เก็บ
                continue
            cur = conn.execute(
                "SELECT announce_type FROM projects_seen WHERE project_id=?", (r["project_id"],)
            ).fetchone()
            if cur:
                if _stage_rank(r["announce_type"]) > _stage_rank(cur[0]):
                    conn.execute(
                        "UPDATE projects_seen SET announce_type=?, stage_updated_at=? WHERE project_id=?",
                        (r["announce_type"], now, r["project_id"]))
                    advanced += 1
                else:
                    skipped += 1
                continue
            conn.execute("""
                INSERT INTO projects_seen
                  (project_id, announce_type, province, budget, project_name,
                   dept_id, dept_name, extraction_confidence, source, first_seen_at,
                   announce_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r["project_id"], r["announce_type"], r["province"], r["budget"],
                r["project_name"], "", r["dept_name"], "hard_province_api",
                "province_api", now, r.get("announce_date") or "",
            ))
            new += 1
        conn.commit()
    finally:
        conn.close()
    return new, skipped, advanced


def mark_discovery_confirmed(project_ids: list[str]) -> int:
    """ประทับ discovery_confirmed=1 ให้ project ที่ Discovery scan เจอ (claim งาน RSS-first).
    UPDATE เท่านั้น — งานที่มี project_locations row อยู่แล้ว (RSS Notifier insert pending).
    คืนจำนวน row ที่ประทับ (rowcount)."""
    if not project_ids:
        return 0
    conn = sqlite3.connect(_db_path())
    try:
        marked = 0
        for pid in project_ids:
            cur = conn.execute(
                "UPDATE project_locations SET discovery_confirmed=1 "
                "WHERE project_id=? AND discovery_confirmed=0", (pid,))
            marked += cur.rowcount
        conn.commit()
        return marked
    finally:
        conn.close()


def count_rss_gap() -> int:
    """นับงาน RSS-first ที่ resolve เป็นจังหวัดเป้าหมายแล้ว แต่ Discovery ยังไม่ประทับตรา.
    = สัญญาณ 'Discovery อาจพลาด' (province-level, ใช้ใน per-sweep report)."""
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM project_locations pl
            JOIN projects_seen ps ON ps.project_id = pl.project_id
            WHERE ps.source='rss' AND pl.discovery_confirmed=0
              AND pl.province_name IN ('นครพนม','บึงกาฬ')
        """).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default="", help="ใส่ token ตรงๆ (= ManualProvider)")
    ap.add_argument("--provider", default="", help="manual|chrome9222|playwright (default: env BMS_TOKEN_PROVIDER)")
    ap.add_argument("--moi", action="append", help="moiId (default: ทุกจังหวัดเป้าหมาย)")
    ap.add_argument("--budget-year", default="2569")
    ap.add_argument("--filter-amphoe", action="store_true", help="กรองเฉพาะ อ.เป้าหมาย")
    ap.add_argument("--ingest", action="store_true", help="เขียนลง projects_seen")
    ap.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงาน")
    ap.add_argument("--worker", action="store_true",
                    help="read-only: อ่าน token จาก cache ไม่ harvest (สำหรับ VPS)")
    ap.add_argument("--full", action="store_true",
                    help="full re-paginate (ปิด incremental — สำหรับ backfill/safety sweep)")
    ap.add_argument("--announce-types", default=os.environ.get("BMS_ANNOUNCE_TYPES", "2"),
                    help="comma list: 2=D0(ประมูล) 1=B0(รับฟังคำวิจารณ์). เช่น '1,2' ดึงทั้งคู่ "
                         "(default จาก env BMS_ANNOUNCE_TYPES)")
    args = ap.parse_args()

    # token ผ่าน Token Service — VPS เป็น worker (allow_refresh=False) อ่าน token ที่ Windows push มา
    from token_service import TokenService, make_provider
    worker = args.worker or os.environ.get("BMS_TOKEN_WORKER") == "1"
    provider = (make_provider("manual", token=args.token) if args.token
                else make_provider(args.provider))
    svc = TokenService(provider, allow_refresh=not worker)
    token = svc.get_valid_token()
    if not token:
        h = svc.health()
        print(f"❌ ไม่ได้ token (provider={provider.name}, state={h['state']}, err={h.get('last_error')})")
        print("   ใส่ --token <value> หรือ env BMS_ANNOUNCEMENT_TOKEN หรือ --provider chrome9222")
        sys.exit(1)
    print(f"🔑 token OK (provider={svc.health()['provider']}, เหลือ {svc.health()['remaining_sec']}s)")

    moi_ids = args.moi or list(PROVINCE_MOI.keys())
    print(f"🔍 Province Discovery — budgetYear={args.budget_year}, จังหวัด={[PROVINCE_MOI.get(m,m) for m in moi_ids]}")

    # incremental เมื่อ ingest จริง + ไม่ --full (dry-run/full = paginate เต็มเพื่อเห็นทั้งหมด)
    incremental = args.ingest and not args.dry_run and not args.full
    # โหลด known เสมอเมื่อ ingest จริง: incremental ใช้หยุด, full ใช้ reconcile (snapshot ก่อนรัน)
    known = _all_known_ids() if (args.ingest and not args.dry_run) else None
    if incremental:
        print(f"⚡ incremental mode — known {len(known)} (หยุดเมื่อรู้หมด {INCR_KNOWN_STOP} หน้าติดกัน, --full ปิด)")
    elif args.full and known is not None:
        print(f"\U0001f504 full sweep — known {len(known)} (paginate ครบ + reconcile incremental)")

    ann_types = [t.strip() for t in args.announce_types.split(",") if t.strip()]
    _AT_LABEL = {"1": "B0/รับฟังคำวิจารณ์", "2": "D0/ประมูล"}
    all_recs = []
    partial_abort = False
    try:
        for at in ann_types:   # B0 ก่อน D0 (ถ้ามีทั้งคู่) → early-stage ได้ tag ก่อนถ้า project ซ้ำ
            print(f"\n📡 announceType={at} ({_AT_LABEL.get(at, at)})")
            for moi in moi_ids:
                province = PROVINCE_MOI.get(moi, moi)
                items = fetch_all_d0(token, moi, args.budget_year,
                                     known_ids=(known if incremental else None),
                                     announce_type=at)
                recs = [normalize(it, province) for it in items]
                all_recs.extend(recs)
    except RateLimited as e:
        # A (fix 2026-06-02): rate-limit → ไม่ทิ้ง! เก็บ all_recs ที่ paginate ได้แล้ว →
        # reconcile/ingest ต่อด้วย partial (เดิม sys.exit(2) ทิ้งทั้งหมด = full sweep เสียเปล่า
        # ทุกวันเพราะ 2 จังหวัด = 128 หน้า > 99 req limit → safety net ไม่เคยทำงาน)
        partial_abort = True
        print(f"\n⚠️ rate-limited — paginate ได้ {len(all_recs)} รายการก่อนชน ({e}) → ดำเนินต่อด้วย partial")

    if not all_recs:
        print("\n⚠️ ไม่ได้ข้อมูล — ตรวจ token (อาจหมดอายุ 30 นาที)")
        _write_heartbeat("no_data", total=0)
        sys.exit(2)

    active = [r for r in all_recs if r["project_status"] != "R"]
    print(f"\n📊 รวม {len(all_recs)} รายการ ({len(active)} active, {len(all_recs)-len(active)} ยกเลิก)")

    # reconciliation (full sweep เท่านั้น): งานใหม่ announceDate เก่า = incremental น่าจะพลาด → alert
    if args.full and known is not None:
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(days=RECONCILE_DAYS)).isoformat()
        missed = [r for r in active if r["project_id"] not in known
                  and r["announce_date"] and r["announce_date"] < cutoff]
        if missed:
            sample = ", ".join(f"{m['project_id']}({m['announce_date']})" for m in missed[:5])
            msg = (f"⚠️ BMS reconcile: full sweep เจอ {len(missed)} งานใหม่ announceDate < {cutoff} "
                   f"= incremental น่าจะพลาด → ตรวจ ordering assumption!\n{sample}")
            print(msg)
            _discord(msg)
        else:
            print("✅ reconcile: ไม่มีงานเก่าที่ incremental พลาด (ordering assumption ยังถือ)")

    target = [r for r in active if in_target_amphoe(r)]
    print(f"🎯 ในอำเภอเป้าหมาย: {len(target)} รายการ")
    for r in target[:20]:
        print(f"   - {r['project_id']} | {r['dept_name'][:28]:28} | ฿{r['budget']:>12,} | {r['project_name'][:45]}")

    chosen = target if args.filter_amphoe else active
    ingested = 0
    marked = 0
    if args.ingest and not args.dry_run:
        ingested, skipped, advanced = ingest(chosen)
        print(f"\n💾 ingest: +{ingested} ใหม่, {advanced} เลื่อน stage, {skipped} เดิม (source=province_api)")
        # RSS Shadow Mode: ประทับตรา discovery_confirmed=1 ให้ทุก project ที่ scan เจอ (claim RSS-first)
        marked = mark_discovery_confirmed([r["project_id"] for r in active])
        print(f"🏷  ประทับตรา Discovery: {marked} งาน (claim RSS-first)")
    else:
        print(f"\n(dry-run — จะ ingest {len(chosen)} รายการ ถ้าใส่ --ingest)")
    _write_heartbeat("ok", total=len(all_recs), active=len(active), ingested=ingested,
                     partial=partial_abort)
    if partial_abort:
        print("⚠️ partial sweep (ชน rate limit) — reconcile/ingest ทำกับจังหวัดที่ paginate ได้แล้ว")

    # full sweep marker per-province (ให้ discovery_catchup รู้ว่า full รอบนี้สำเร็จครบ)
    # เขียนเฉพาะ full + 1 จังหวัด + ครบ (ไม่ partial) → ถ้า partial/พลาด catchup จะ retry
    if args.full and len(moi_ids) == 1 and args.ingest and not args.dry_run and not partial_abort:
        try:
            fmpath = os.path.join(os.environ.get("BMS_DATA_DIR", "/opt/bms/data"),
                                  f"last_fullsweep_{moi_ids[0]}.json")
            with open(fmpath, "w", encoding="utf-8") as f:
                json.dump({"ts": _utc_now(), "moi": moi_ids[0]}, f, ensure_ascii=False)
            print(f"📍 full sweep marker เขียนแล้ว: {moi_ids[0]}")
        except Exception:
            pass

    # RSS Shadow Mode: per-sweep report (รายงานเสมอ จบทุก full sweep — 4 ครั้ง/วัน)
    if args.full and args.ingest and not args.dry_run:
        from datetime import datetime as _dtf, timezone as _tzf, timedelta as _tdf
        now_th_f = _dtf.now(_tzf(_tdf(hours=7))).strftime("%H:%M")
        prov_f = PROVINCE_MOI.get(moi_ids[0], moi_ids[0]) if len(moi_ids) == 1 else "ทุกจังหวัด"
        gap = count_rss_gap()
        gap_line = (f"RSS เห็นแต่ Discovery ยังไม่เจอ: {gap} งาน "
                    + ("✅" if gap == 0 else "⚠️ ดู audit รายวัน"))
        _discord("\n".join([
            f"🔍 Full sweep {prov_f} จบ ({now_th_f})",
            f"• scan เจอ: {len(active)} งาน",
            f"• ประทับตรา Discovery: {marked} งาน (ใหม่ {ingested})",
            f"• {gap_line}",
        ]))

    # Discord notify ทุกรอบ incremental (7/13/19) — เจอ/ไม่เจองานใหม่ + รายละเอียด (กัญจน์ขอ 2026-06-01)
    # ไม่รวม full-sweep (safety net เงียบ — มี reconcile alert แยกถ้าเจอปัญหา)
    if args.ingest and not args.dry_run and not args.full:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td2
        now_th = _dt.now(_tz(_td2(hours=7))).strftime("%H:%M")
        prov_latest = {}
        for r in all_recs:
            p, ad = r["province"], r["announce_date"]
            if ad and (p not in prov_latest or ad > prov_latest[p]):
                prov_latest[p] = ad
        latest_str = " · ".join(f"{p} {dt}" for p, dt in prov_latest.items()) or "—"
        new_recs = [r for r in chosen if known is not None and r["project_id"] not in known]
        if ingested > 0:
            lines = [f"🆕 Discovery {now_th} — เจอ {ingested} งานใหม่!",
                     f"scan {len(all_recs)} ({len(active)} active) · ในอำเภอเป้าหมาย {len(target)}",
                     f"announce ล่าสุด: {latest_str}", "งานใหม่:"]
            for r in new_recs[:8]:
                lines.append(f"  • {r['province']} | ฿{r['budget']:,} | {r['project_name'][:42]}")
            _discord("\n".join(lines))
        else:
            _discord(f"✅ Discovery {now_th} — ตรวจแล้วไม่มีงานใหม่\n"
                     f"scan {len(all_recs)} ({len(active)} active, {len(all_recs)-len(active)} ยกเลิก) · known ครบ\n"
                     f"announce ล่าสุด: {latest_str} (ตลาดตามนี้)")


if __name__ == "__main__":
    main()
