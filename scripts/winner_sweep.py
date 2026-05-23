"""
winner_sweep.py — daily winner sweep สำหรับ pending_award (Hybrid: CGD + eGP)

Old pending (> min-age-days) เท่านั้น — recent ครอบคลุมโดย refresh_active_jobs --expand แล้ว

Strategy:
  1st pass: CGD egp-contact-2568 (province-filtered batch) — fast, ~3 min/7K jobs
             ครอบคลุมงานปีงบฯ 2568 (ต.ค. 68 - ก.ย. 69) ที่มี province ใน pending_award
  2nd pass: eGP getProcureResult rotation — max-egp jobs/day (cursor)
             ครอบคลุมปีเก่า + ไม่มี province + CGD miss

Updates data/winner_cache_bootstrap.json
"""

import os, sys, json, re, time, argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

import requests
from sheets_client import open_sheet
from process5_http_client import get_procure_result

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
WINNER_CACHE   = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
SWEEP_CURSOR   = Path(__file__).parent.parent / "data" / "winner_sweep_cursor.json"

CKAN_BASE = "https://opend.data.go.th/get-ckan"
CGD_CONTRACT_RIDS = [
    "e4eaa1b4-eb1a-4534-b227-988ee25b898d",
    "9ae119c4-73b9-4bb6-9b71-7b355269bc00",
    "1c1a90af-2d47-4bfb-ae87-e479b2582257",
    "c2385bd6-7e2a-40c2-94d8-6a65824c9415",
    "bb538ac1-3455-446d-b975-d709d6439e72",
    "5b98d6ba-0f66-4bb1-b8db-9b9aae928171",
    "037adcca-b349-44f6-9686-9fd1e9182227",
    "26316135-a95f-40e3-b2e8-1c912046c0ed",
    "882332c4-1f60-4db7-9962-9062eb08f6c4",
    "35961821-d945-4fc0-8ce1-a96b4cd46bd6",
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_cache() -> dict:
    if WINNER_CACHE.exists():
        return json.loads(WINNER_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict):
    WINNER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WINNER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _pct(budget, price) -> str:
    try:
        b = float(str(budget).replace(",", "").strip())
        p = float(str(price).replace(",", "").strip())
        return f"{((b - p) / b) * 100:.2f}" if b > 0 else ""
    except Exception:
        return ""


def _parse_thai_date(s: str) -> Optional[datetime]:
    s = str(s).strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            d = datetime.strptime(s, fmt)
            if d.year >= 2400:
                d = d.replace(year=d.year - 543)
            return d
        except ValueError:
            continue
    return None


def _is_company_name(val) -> bool:
    """Heuristic: field value เป็นชื่อบริษัท/หน่วยงานไทย"""
    if not val or not isinstance(val, str):
        return False
    s = str(val).strip()
    if not s or len(s) < 4:
        return False
    if s.startswith("POINT") or s.startswith("ระหว่าง"):
        return False
    if not re.search(r'[฀-๿]', s):   # ต้องมี Thai text
        return False
    if re.match(r'^\d{1,2}\s*[฀-๿]', s):   # Thai date: "10 ธ.ค."
        return False
    if re.fullmatch(r'[\d,.\s]+', s):           # pure number
        return False
    return True


def _extract_winner_from_cgd(rec: dict) -> tuple[str, str, str]:
    """
    Extract (winner_name, winning_price, award_date) จาก CGD record
    รองรับ column drift: 3 extra cols inserted after จังหวัด ทำให้ winner name
    ถูก shift ไปอยู่ที่ field 'ละติจูดโครงการ' แทน 'ชื่อผู้ชนะ'
    """
    winner = ""
    for field in ["ละติจูดโครงการ", "ชื่อผู้ชนะ", "เลขนิติบุคคล", "ลองจิจูดโครงการ"]:
        if _is_company_name(rec.get(field)):
            winner = str(rec[field]).strip()
            break

    price = str(rec.get("ราคาตกลงซื้อ/จ้าง") or "").strip()
    budget = str(rec.get("งบประมาณ(บาท)") or "").strip()

    award_date = ""
    # Signing date อยู่ที่ เลขนิติบุคคล (drift) หรือ วันที่ลงนามสัญญา (ถ้าไม่ drift)
    for field in ["เลขนิติบุคคล", "วันที่ลงนามสัญญา"]:
        v = str(rec.get(field) or "").strip()
        if v and re.search(r'\d', v) and re.search(r'[฀-๿]', v):
            award_date = v
            break

    return winner, price, award_date


_SCHEMA_CACHE: dict[str, list[str]] = {}  # rid → [field_name, ...] in order


def _get_cgd_schema(rid: str, token: str) -> list[str]:
    """ดึง field order จริงจาก CKAN datastore_info — cache per rid"""
    if rid in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[rid]
    try:
        r = requests.get(
            f"{CKAN_BASE}/datastore_info",
            params={"resource_id": rid},
            headers={"api-key": token, "Accept": "application/json"},
            timeout=15,
        )
        if r.ok:
            fields = r.json().get("result", {}).get("fields", [])
            names = [f["id"] for f in fields if "id" in f]
            if names:
                _SCHEMA_CACHE[rid] = names
                return names
    except Exception:
        pass
    return []


def _cgd_datastore_search(rid: str, province: str, token: str,
                           limit: int = 1000, offset: int = 0) -> Optional[dict]:
    params = {
        "resource_id": rid,
        "limit": limit,
        "offset": offset,
        "filters": json.dumps({"จังหวัด": province}),
    }
    try:
        r = requests.get(f"{CKAN_BASE}/datastore_search",
                         params=params,
                         headers={"api-key": token, "Accept": "application/json"},
                         timeout=30)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def _winner_fields_from_schema(schema: list[str]) -> tuple[str, str, str]:
    """
    คืน (winner_field, price_field, date_field) จาก schema จริง
    ถ้า schema ไม่มี หรือ field drift → fallback ไป heuristic เดิม
    """
    # หา winner field: ชื่อผู้ชนะ ก่อน — ถ้าไม่มีใน schema แสดงว่า drift
    winner_candidates = ["ชื่อผู้ชนะ", "ละติจูดโครงการ", "เลขนิติบุคคล", "ลองจิจูดโครงการ"]
    price_candidates  = ["ราคาตกลงซื้อ/จ้าง", "เลขที่สัญญา"]
    date_candidates   = ["วันที่ลงนามสัญญา", "เลขนิติบุคคล"]

    winner = next((f for f in winner_candidates if f in schema), winner_candidates[0])
    price  = next((f for f in price_candidates  if f in schema), price_candidates[0])
    date   = next((f for f in date_candidates   if f in schema), date_candidates[0])
    return winner, price, date


def _fetch_cgd_for_province(province: str, token: str, call_budget: int) -> tuple[dict, int]:
    """
    Download ทุก record ของ province จาก CGD (ทุก 10 files, paginate)
    Returns: ({projectId: winner_info}, calls_used)
    """
    result: dict[str, dict] = {}
    calls = 0

    for rid in CGD_CONTRACT_RIDS:
        if calls >= call_budget:
            break

        # ดึง schema จริงจาก CKAN เพื่อ map field ที่ drift ได้ถูกต้อง
        schema = _get_cgd_schema(rid, token)
        winner_f, price_f, date_f = _winner_fields_from_schema(schema)

        offset = 0
        while calls < call_budget:
            data = _cgd_datastore_search(rid, province, token, limit=1000, offset=offset)
            calls += 1
            if data is None:
                break
            records = data.get("result", {}).get("records", [])
            if not records:
                break
            total = data.get("result", {}).get("total", 0)

            for rec in records:
                pid = str(rec.get("รหัสโครงการ", "")).strip()
                if not pid:
                    continue
                # ลอง schema-aware field ก่อน → fallback ไป heuristic ถ้าค่าผิดปกติ
                winner = str(rec.get(winner_f, "") or "").strip()
                if not _is_company_name(winner):
                    # schema field ไม่ถูก (drift) → heuristic scan
                    winner, price, award_date = _extract_winner_from_cgd(rec)
                else:
                    price      = str(rec.get(price_f, "") or "").strip()
                    award_date = str(rec.get(date_f, "")  or "").strip()

                if winner:
                    result[pid] = {
                        "winner_name": winner,
                        "winner_price": price,
                        "discount_pct": _pct(rec.get("งบประมาณ(บาท)"), price),
                        "award_date": award_date,
                    }

            offset += len(records)
            if offset >= total:
                break

    return result, calls


def sweep_cgd(old_jids_by_province: dict[str, list[str]], token: str, max_calls: int) -> tuple[dict, set]:
    """
    CGD batch sweep — provinces sorted by job count (ดึงจังหวัดสำคัญก่อน)
    Returns: (winner_updates, matched_jids_set)
    """
    if not token:
        log("  ⚠️ OPEND_USER_TOKEN ไม่ set — ข้าม CGD sweep")
        return {}, set()

    updates: dict[str, dict] = {}
    matched: set[str] = set()
    calls_left = max_calls

    sorted_provinces = sorted(old_jids_by_province.items(), key=lambda x: -len(x[1]))

    for province, jids in sorted_provinces:
        if calls_left <= 0:
            log(f"  CGD: budget หมด ({max_calls} calls) — {len(sorted_provinces) - list(p for p, _ in sorted_provinces).index(province)} จังหวัดเหลือ → eGP")
            break
        log(f"  CGD: {province} ({len(jids)} jobs)...")
        prov_data, used = _fetch_cgd_for_province(province, token, calls_left)
        calls_left -= used
        log(f"    → {len(prov_data)} winners | used {used} calls (เหลือ {calls_left})")

        for jid in jids:
            if jid in prov_data:
                updates[jid] = prov_data[jid]
                matched.add(jid)

    return updates, matched


def sweep_egp(jids: list[str], budget_map: dict[str, str], workers: int) -> dict:
    """eGP getProcureResult สำหรับ list of jids (parallel)"""

    def _fetch(jid: str):
        winfo = get_procure_result(jid)
        if winfo.get("winner"):
            price = winfo.get("winning_price", "")
            return jid, {
                "winner_name": winfo["winner"],
                "winner_price": str(price),
                "discount_pct": _pct(budget_map.get(jid, ""), price),
                "award_date": winfo.get("announce_date", ""),
            }
        return jid, None

    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch, jid): jid for jid in jids}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            done += 1
            jid, winner = future.result()
            if winner:
                results[jid] = winner
            if done % 50 == 0:
                log(f"    [{done}/{len(jids)}] {len(results)} winners so far...")

    return results


def _deadline_priority_select(jids: list[str], max_n: int,
                               deadline_map: dict[str, datetime]) -> list[str]:
    """
    เลือก max_n jobs จาก jids โดยให้ priority กับงานที่ deadline ผ่านมาใหม่สุด

    Tier A (deadline 0-60 วันที่ผ่านมา): เช็คทุกวัน — ตรวจเจอผู้ชนะวันเดียวกัน
    Tier B (deadline >60 วัน หรือไม่รู้): หมุนวน cursor เหมือนเดิม

    แก้ปัญหา: งานที่ประกาศผลวันนี้เจอภายใน 1-2 วัน แทน 25 วัน
    """
    if max_n <= 0:
        return []
    if len(jids) <= max_n:
        return jids

    today = datetime.now()
    HIGH_PRIORITY_DAYS = 60  # deadline ผ่านมาไม่เกิน 60 วัน → ตรวจทุกวัน

    tier_a, tier_b = [], []
    for jid in jids:
        dl = deadline_map.get(jid)
        if dl:
            days_past = (today - dl).days
            if 0 <= days_past <= HIGH_PRIORITY_DAYS:
                tier_a.append((jid, days_past))
            else:
                tier_b.append(jid)
        else:
            tier_b.append(jid)

    # Tier A: เรียงจาก deadline ผ่านมาใหม่สุด (งานสดกว่า → priority สูงกว่า)
    tier_a.sort(key=lambda x: x[1])
    tier_a_jids = [jid for jid, _ in tier_a]

    selected = tier_a_jids[:max_n]
    remaining = max_n - len(selected)

    # Tier B: หมุนวน cursor สำหรับงานเก่า (backlog เคลียร์ช้าๆ)
    if remaining > 0 and tier_b:
        off = 0
        if SWEEP_CURSOR.exists():
            try:
                off = int(json.loads(SWEEP_CURSOR.read_text(encoding="utf-8")).get("offset", 0))
            except Exception:
                off = 0
        off %= len(tier_b)
        sel_b = (tier_b + tier_b)[off:off + remaining]
        selected.extend(sel_b)
        SWEEP_CURSOR.write_text(
            json.dumps({"offset": (off + remaining) % len(tier_b),
                        "total_tier_b": len(tier_b),
                        "updated": datetime.now().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )

    return selected


def _load_env():
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main():
    ap = argparse.ArgumentParser(
        description="Daily winner sweep: CGD batch (old pending) + eGP rotation (fallback)")
    ap.add_argument("--min-age-days", type=int, default=30,
                    help="ตรวจเฉพาะงาน publish > N วัน (recent ครอบคลุมโดย refresh แล้ว)")
    ap.add_argument("--max-cgd-calls", type=int, default=200,
                    help="max CGD API calls ต่อรอบ (quota 1000/วัน)")
    ap.add_argument("--max-egp", type=int, default=400,
                    help="max eGP getProcureResult calls ต่อรอบ (rotation สำหรับ CGD miss)")
    ap.add_argument("--workers", type=int, default=5,
                    help="parallel workers สำหรับ eGP sweep")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    _load_env()
    cgd_token = os.environ.get("OPEND_USER_TOKEN", "")

    log("=" * 60)
    log("Winner Sweep — Hybrid (CGD batch + eGP rotation)")
    log(f"  min-age-days={args.min_age_days} | max-cgd-calls={args.max_cgd_calls}"
        f" | max-egp={args.max_egp} | workers={args.workers}")
    log("=" * 60)

    # ── อ่าน pending_award ──
    log("Reading pending_award...")
    ws = open_sheet(SPREADSHEET_ID, "pending_award")
    rows = ws.get_all_values()
    hdrs = rows[0]
    h = {col: i for i, col in enumerate(hdrs)}
    pub_i      = h.get("publish_date", -1)
    prov_i     = h.get("province", -1)
    budget_i   = h.get("budget", -1)
    deadline_i = h.get("deadline", -1)

    cache = _load_cache()
    today = datetime.now()

    old_by_province: dict[str, list[str]] = {}  # province → [jid]
    old_no_province: list[str] = []
    budget_map:   dict[str, str]      = {}
    deadline_map: dict[str, datetime] = {}  # jid → deadline datetime (สำหรับ priority sort)

    for r in rows[1:]:
        if not r or not r[0]:
            continue
        jid = r[0].strip()
        if jid in cache:
            continue   # winner รู้แล้ว — skip
        pub      = r[pub_i].strip()      if 0 <= pub_i < len(r)      else ""
        prov     = r[prov_i].strip()     if 0 <= prov_i < len(r)     else ""
        deadline = r[deadline_i].strip() if 0 <= deadline_i < len(r) else ""
        budget_map[jid] = r[budget_i].strip() if 0 <= budget_i < len(r) else ""

        d = _parse_thai_date(pub)
        age_days = (today - d).days if d else 999
        if age_days < args.min_age_days:
            continue   # recent → refresh handles it

        dl = _parse_thai_date(deadline)
        if dl:
            deadline_map[jid] = dl

        if prov:
            old_by_province.setdefault(prov, []).append(jid)
        else:
            old_no_province.append(jid)

    total_old = sum(len(v) for v in old_by_province.values()) + len(old_no_province)
    log(f"  old pending (>{args.min_age_days}d, not in cache): {total_old}")
    log(f"    → with province: {total_old - len(old_no_province)} ({len(old_by_province)} provinces)")
    log(f"    → no province:   {len(old_no_province)}")
    log(f"  winner_cache: {len(cache)} known entries")

    if total_old == 0:
        log("✅ ไม่มี old pending ที่ต้องตรวจ")
        return

    if args.dry_run:
        log("\n[DRY-RUN] ไม่เรียก API จริง")
        for prov, jids in sorted(old_by_province.items(), key=lambda x: -len(x[1]))[:5]:
            log(f"  {prov}: {len(jids)} jobs")
        return

    new_winners = 0

    # ── Pass 1: CGD batch ──
    log(f"\n[Pass 1] CGD batch (max {args.max_cgd_calls} calls)...")
    t0 = datetime.now()
    cgd_updates, cgd_matched = sweep_cgd(old_by_province, cgd_token, args.max_cgd_calls)
    cache.update(cgd_updates)
    new_winners += len(cgd_updates)
    elapsed = int((datetime.now() - t0).total_seconds())
    log(f"  ✅ CGD: +{len(cgd_updates)} winners | {elapsed}s")

    # ── Pass 2: eGP rotation (CGD miss + no-province) ──
    unmatched_jids: list[str] = []
    for jids in old_by_province.values():
        for jid in jids:
            if jid not in cgd_matched:
                unmatched_jids.append(jid)
    unmatched_jids.extend(old_no_province)

    if unmatched_jids and args.max_egp > 0:
        sel = _deadline_priority_select(unmatched_jids, args.max_egp, deadline_map)
        tier_a_cnt = sum(1 for j in sel if deadline_map.get(j) and
                         0 <= (today - deadline_map[j]).days <= 60)
        log(f"\n[Pass 2] eGP priority: {len(sel)}/{len(unmatched_jids)} unmatched "
            f"(tier_a={tier_a_cnt} recent ≤60d | tier_b={len(sel)-tier_a_cnt} old | workers={args.workers})")
        t0 = datetime.now()
        egp_updates = sweep_egp(sel, budget_map, args.workers)
        cache.update(egp_updates)
        new_winners += len(egp_updates)
        elapsed = int((datetime.now() - t0).total_seconds())
        log(f"  ✅ eGP: +{len(egp_updates)} winners | {elapsed}s")
    else:
        log(f"\n[Pass 2] ข้าม (unmatched={len(unmatched_jids)}, max-egp={args.max_egp})")

    # ── Save ──
    if new_winners:
        _save_cache(cache)
        log(f"\n+{new_winners} winners → winner_cache (รวม {len(cache)})")
    else:
        log("\n(ไม่มี winner ใหม่ในรอบนี้)")

    log(f"\n✅ Winner Sweep เสร็จ | +{new_winners} new winners")


if __name__ == "__main__":
    main()
