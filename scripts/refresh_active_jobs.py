"""
refresh_active_jobs.py — รีเฟรชสถานะงาน active_bidding จาก eGP API สด

HTTP-only version (2026-05-19): ไม่ต้องใช้ Chrome อีกต่อไป
ใช้ process5_http_client (Mozilla UA + Referer) แทน

วิธีใช้:
    python scripts/refresh_active_jobs.py [--jids id1,id2,...] [--all]
    python scripts/refresh_active_jobs.py --from-queue     # ingest จาก rss_queue.json
    python scripts/refresh_active_jobs.py --expand         # refresh active + tor_review + pending_award
    python scripts/refresh_active_jobs.py --workers 5      # parallel (default 3)
"""

import sys
import json
import time
import argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import open_sheet
from process5_http_client import get_project_detail, get_procure_result

SPREADSHEET_ID   = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
WINNER_CACHE     = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
PENDING_CURSOR   = Path(__file__).parent.parent / "data" / "refresh_pending_cursor.json"


def _parse_thai_date(s: str):
    """แปลงวันที่ DD/MM/YYYY (รองรับ พ.ศ.) หรือ ISO → datetime หรือ None"""
    s = str(s).strip()[:10]
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            d = datetime.strptime(s, fmt)
            if d.year >= 2400:          # พ.ศ. → ค.ศ.
                d = d.replace(year=d.year - 543)
            return d
        except ValueError:
            continue
    return None


def _rotate_old(jids: list[str], max_n: int) -> list[str]:
    """หมุนวน (cursor) เลือก max_n จาก jids — สำหรับ pending เก่า (เก็บตก/เคลียร์งานตาย)
    max_n=0 → skip ทั้งหมด | max_n<0 → ไม่จำกัด | max_n>0 → rotate
    """
    if max_n == 0:
        return []   # skip all old pending explicitly
    if max_n < 0 or len(jids) <= max_n:
        return jids
    off = 0
    if PENDING_CURSOR.exists():
        try:
            off = int(json.loads(PENDING_CURSOR.read_text(encoding="utf-8")).get("offset", 0))
        except (json.JSONDecodeError, ValueError):
            off = 0
    off %= len(jids)
    sel = (jids + jids)[off:off + max_n]   # wrap-around
    PENDING_CURSOR.write_text(
        json.dumps({"offset": (off + max_n) % len(jids), "total": len(jids),
                    "updated": datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8",
    )
    return sel


def _select_pending(pairs: list[tuple], recent_days: int, max_old: int) -> list[str]:
    """
    pairs = [(job_id, publish_date), ...]
    คืน job_ids ที่จะ refresh:
      - max_old=0 → skip ทั้งหมด (recent + old) — ใช้เมื่อต้องการรัน active+tor เท่านั้น
      - งานประกาศ ≤ recent_days วัน → เช็คทุกวัน (อยู่ในช่วงลุ้นผู้ชนะ ~9 วันหลังปิดซอง)
      - งานเก่ากว่านั้น → หมุนวน max_old/รอบ (เก็บตกผู้ชนะที่ประกาศช้า + เคลียร์งานตาย)
    """
    if max_old == 0:
        return []  # skip all pending — ลด runtime สำหรับ daily pipeline
    today = datetime.now()
    recent, old = [], []
    for jid, pub in pairs:
        d = _parse_thai_date(pub)
        if d and 0 <= (today - d).days <= recent_days:
            recent.append(jid)
        else:
            old.append(jid)
    return recent + _rotate_old(old, max_old)

# Note: เคยมี deptid_province_map.json — ลบ design ทิ้ง เพราะ dept ใหญ่มีหลายสาขา
# การเก็บ province ของ project แรกเป็น HQ ของ dept ทั้งหมดทำให้ routing ลูกค้าผิด

# ── Province extraction ──────────────────────────────────────────
# ใช้ province_extractor: cascade 8 ชั้น (prefix → org-cache → bare matching)
# แทน substring-only เดิม — ดู scripts/province_extractor.py
# สำคัญ: ต้องส่ง dept_name + title แยกกัน (org-cache ใช้ exact-match บน dept_name)
from province_extractor import extract_province as extract_province


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def calc_pct_discount(budget_str, price_str: str) -> str:
    try:
        budget = float(str(budget_str).replace(",", "").strip())
        price  = float(str(price_str).replace(",", "").strip())
        if budget > 0:
            return f"{((budget - price) / budget) * 100:.2f}"
    except (ValueError, TypeError):
        pass
    return ""


def load_winner_cache() -> dict:
    if WINNER_CACHE.exists():
        return json.loads(WINNER_CACHE.read_text(encoding="utf-8"))
    return {}


def save_winner_cache(cache: dict):
    WINNER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WINNER_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _process_one(jid: str, budget: str) -> dict:
    """
    ประมวลผล 1 job → คืน dict ที่มี fields ที่ต้องอัปเดต + winner info
    ใช้ process5_http_client โดยตรง (ไม่ต้อง Chrome)
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    fields  = {"last_seen_at": now_iso}
    winner  = {}

    detail = get_project_detail(jid)
    fields["api_validity_state"] = "active" if detail.get("valid") else "retired"

    if detail.get("valid"):
        stepId  = detail.get("step_id", "")
        ps_raw  = detail.get("project_status_raw", "")
        a_type  = detail.get("announce_type", "")
        seqno   = detail.get("flow_seqno", 0)

        fields["step_id"]            = stepId
        fields["project_status_raw"] = ps_raw
        fields["announce_type"]      = a_type

        new_status = detail.get("project_status", "")
        if new_status:
            fields["project_status"] = new_status

        is_cancelled = (ps_raw == "R") or (a_type in ("D1", "W1"))
        if is_cancelled:
            fields["project_status"] = "ยกเลิก"

    if ps_raw := fields.get("project_status_raw", ""):
        if ps_raw != "R":
            winfo = get_procure_result(jid)
            if winfo.get("winner"):
                price = winfo.get("winning_price", "")
                pct   = calc_pct_discount(budget, price)
                winner = {
                    "winner_name":  winfo["winner"],
                    "winner_price": str(price),
                    "discount_pct": pct,
                    "award_date":   winfo.get("announce_date", ""),
                }
                fields["project_status"] = "ประมูลแล้ว"
    else:
        # ถ้า detail ไม่ valid → ลองดู winner อยู่ดี (conservative — recall > precision)
        winfo = get_procure_result(jid)
        if winfo.get("winner"):
            price = winfo.get("winning_price", "")
            pct   = calc_pct_discount(budget, price)
            winner = {
                "winner_name":  winfo["winner"],
                "winner_price": str(price),
                "discount_pct": pct,
                "award_date":   winfo.get("announce_date", ""),
            }
            fields["project_status"] = "ประมูลแล้ว"

    return {"fields": fields, "winner": winner, "detail_valid": detail.get("valid", False)}


def _build_sparse_row(jid: str, q_item: dict, detail: dict) -> list:
    """สร้าง sparse row 26 cols สำหรับ new job จาก RSS queue + getProjectDetail"""
    from classifier_tags import classify_all, TAG_COLUMNS

    now_iso = datetime.now().isoformat(timespec="seconds")
    title      = q_item.get("title", "")
    dept_name  = detail.get("dept_sub_name", "")

    # Extract province จาก dept_sub_name + title (longest match first)
    # ── ไม่ fallback ไป deptId map เพราะ dept ใหญ่มีหลายสาขาทั่วประเทศ ──
    # การเก็บ "province ของ project แรก" เป็น HQ ของ dept ผิด design
    # ถ้าหา province ไม่เจอ → ปล่อยว่าง (ลูกค้า filter จังหวัดจะไม่ได้รับ — safe กว่า)
    province = extract_province(dept_name, title)

    row_dict = {
        "title": title,
        "procurement_type": "",
        "budget": "",
        "deadline": "",
        "province": province,
        "district": "",
        "subdistrict": "",
        "announce_type": detail.get("announce_type", ""),
    }
    tags = classify_all(row_dict)

    dept_note = f"keyword:rss | dept:{q_item.get('deptId', '')}"
    base = [
        jid,
        title,
        dept_name,                                       # department (จาก dept_sub_name)
        province,                                        # province (extracted)
        "",                                              # district
        "",                                              # subdistrict
        "",                                              # procurement_type
        "",                                              # budget
        q_item.get("pubDate", ""),                       # publish_date
        "",                                              # deadline
        detail.get("project_status", ""),
        dept_note,
        q_item.get("link", ""),                          # tor_url
        now_iso,                                         # first_seen_at
        now_iso,                                         # last_seen_at
        detail.get("step_id", ""),
        detail.get("project_status_raw", ""),
        detail.get("announce_type", ""),
    ]
    base.extend(tags[col] for col in TAG_COLUMNS)
    # event lineage fields — immutable after first write
    base.extend([
        now_iso,        # discovered_at (set once, never overwritten)
        "rss_scraper",  # ingestion_source
        "v2_process5",  # ingestion_version
    ])
    # operational health fields
    base.extend([
        "0",            # refresh_count (starts at 0 for new jobs)
        "unknown",      # api_validity_state (unknown until first refresh)
    ])
    return base  # 31 cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jids",      help="comma-separated job_ids")
    ap.add_argument("--all",       action="store_true", help="refresh ทุก row ใน active_bidding")
    ap.add_argument("--expand",    action="store_true", help="refresh active + tor_review + pending_award")
    ap.add_argument("--from-queue",action="store_true", help="ingest projectIds จาก data/rss_queue.json")
    ap.add_argument("--dry-run",   action="store_true", help="ไม่ write จริง — แค่ log")
    ap.add_argument("--limit",     type=int, default=0, help="จำกัด jobs (สำหรับ test)")
    ap.add_argument("--workers",   type=int, default=3, help="parallel workers (default 3)")
    ap.add_argument("--pending-recent-days", type=int, default=30,
                    help="pending ที่ประกาศ ≤N วัน → เช็คทุกวัน (ช่วงลุ้นผู้ชนะ)")
    ap.add_argument("--max-pending", type=int, default=1500,
                    help="จำกัด pending 'เก่า' (>recent-days) ต่อรอบ แบบหมุนวน; 0=ไม่จำกัด")
    args = ap.parse_args()

    log("=" * 60)
    log("Refresh Active Jobs — HTTP-only (no Chrome required)")
    log("=" * 60)

    # ── โหลด queue ──
    queue_items: list[dict] = []
    queue_file = Path(__file__).parent.parent / "data" / "rss_queue.json"
    if args.from_queue:
        if queue_file.exists():
            try:
                queue_items = json.loads(queue_file.read_text(encoding="utf-8"))
                if not isinstance(queue_items, list):
                    queue_items = []
            except json.JSONDecodeError:
                queue_items = []
            log(f"  📥 queue: {len(queue_items)} items pending")
        else:
            log(f"  ⚠️ {queue_file} ไม่พบ — queue ว่าง")

    # ── เลือก jobs ──
    if args.from_queue:
        target_jids = [q.get("projectId", "").strip() for q in queue_items if q.get("projectId")]
        target_jids = [j for j in target_jids if j]
        log(f"  from-queue: {len(target_jids)} jobs")
    elif args.jids:
        target_jids = [j.strip() for j in args.jids.split(",") if j.strip()]
        log(f"  targeted refresh: {len(target_jids)} jobs")
    elif args.expand:
        # active + tor = งานที่ลูกค้าประมูลได้/กำลังเปลี่ยน → refresh เต็มทุกรอบ
        core_jids = []
        for sn in ("active_bidding", "tor_review"):
            try:
                ws = open_sheet(SPREADSHEET_ID, sn)
                rows = ws.get_all_values()
                jids = [r[0] for r in rows[1:] if r and r[0]]
                core_jids.extend(jids)
                log(f"  {sn}: +{len(jids)} jobs")
            except Exception as e:
                log(f"  {sn}: error {e}")
        # pending_award = รอประกาศผู้ชนะ (10K+) → จัดลำดับด้วย publish_date กัน timeout
        pending_pairs = []
        try:
            ws = open_sheet(SPREADSHEET_ID, "pending_award")
            rows = ws.get_all_values()
            ph = {h: i for i, h in enumerate(rows[0])}
            pub_i = ph.get("publish_date", -1)
            for r in rows[1:]:
                if r and r[0]:
                    pub = r[pub_i] if 0 <= pub_i < len(r) else ""
                    pending_pairs.append((r[0], pub))
        except Exception as e:
            log(f"  pending_award: error {e}")
        sel_pending = _select_pending(pending_pairs, args.pending_recent_days, args.max_pending)
        log(f"  pending_award: {len(pending_pairs)} total → "
            f"refresh {len(sel_pending)} (recent ≤{args.pending_recent_days}d + old rotate {args.max_pending})")
        target_jids = list(dict.fromkeys(core_jids + sel_pending))
        log(f"  expand mode: {len(target_jids)} unique jobs")
    else:
        ws_act = open_sheet(SPREADSHEET_ID, "active_bidding")
        rows   = ws_act.get_all_values()
        target_jids = [r[0] for r in rows[1:] if r and r[0]]
        log(f"  full refresh: {len(target_jids)} active_bidding jobs")

    if args.limit > 0 and len(target_jids) > args.limit:
        log(f"  --limit applied: ใช้แค่ {args.limit} (จาก {len(target_jids)})")
        target_jids = target_jids[:args.limit]

    if not target_jids:
        log("ไม่มี jobs — เสร็จสิ้น")
        return

    if args.dry_run:
        log("\n🔍 DRY RUN")
        queue_by_pid_dry = {q.get("projectId", ""): q for q in queue_items}
        for jid in target_jids[:20]:
            q_item = queue_by_pid_dry.get(jid, {})
            log(f"  [DRY] {jid}: {q_item.get('title', '')[:60]}")
        if len(target_jids) > 20:
            log(f"  ... และอีก {len(target_jids) - 20} jobs")
        return

    # ── อ่าน all_jobs ──
    log("\nReading all_jobs...")
    ws_all     = open_sheet(SPREADSHEET_ID, "all_jobs")
    all_values = ws_all.get_all_values()
    hdrs       = all_values[0]
    h_idx      = {h: i for i, h in enumerate(hdrs)}

    row_map: dict[str, tuple[int, str]] = {}
    for row_num, r in enumerate(all_values[1:], start=2):
        jid = r[0] if r else ""
        if jid in target_jids:
            budget = r[h_idx.get("budget", 7)] if h_idx.get("budget", -1) < len(r) else ""
            row_map[jid] = (row_num, budget)

    log(f"  matched {len(row_map)} jobs in all_jobs")

    cache = load_winner_cache()
    log(f"  winner cache: {len(cache)} entries")
    log(f"  workers: {args.workers}")

    queue_by_pid = {q.get("projectId", ""): q for q in queue_items}

    # ── Process existing jobs (parallel) ──
    existing_jids = [jid for jid in target_jids if jid in row_map]
    new_jids      = [jid for jid in target_jids if jid not in row_map and jid in queue_by_pid]

    update_payload = []
    new_winners    = 0
    status_updates = 0

    if existing_jids:
        log(f"\nProcessing {len(existing_jids)} existing jobs (workers={args.workers})...")

        def _worker(jid: str):
            row_num, budget = row_map[jid]
            result = _process_one(jid, budget)
            # increment refresh_count from current row value
            r = all_values[row_num - 1]
            rc_i = h_idx.get("refresh_count", -1)
            cur_rc = int(r[rc_i]) if 0 <= rc_i < len(r) and str(r[rc_i]).isdigit() else 0
            result["fields"]["refresh_count"] = str(cur_rc + 1)
            return jid, row_num, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_worker, jid): jid for jid in existing_jids}
            done = 0
            for future in concurrent.futures.as_completed(futures):
                done += 1
                jid, row_num, result = future.result()
                fields = result["fields"]
                winner = result["winner"]
                valid  = result["detail_valid"]

                if valid:
                    status_updates += 1

                if winner:
                    cache[jid] = winner
                    new_winners += 1

                update_payload.append({"row": row_num, "fields": fields})

                if done % 20 == 0:
                    log(f"  [{done}/{len(existing_jids)}] ...")

        log(f"  ✅ {len(existing_jids)} jobs processed")

    # ── Sparse insert สำหรับ jids ใหม่จาก queue ──
    appended_rows: list[list] = []
    processed_pids: set[str]  = set()

    if new_jids:
        log(f"\nProcessing {len(new_jids)} new jobs from RSS queue...")
        for jid in new_jids:
            q_item = queue_by_pid[jid]
            q_atype = q_item.get("anounce_type", "")

            detail = get_project_detail(jid)
            if not detail.get("valid"):
                # P0 (planning) items fail getProjectDetail — save from RSS data directly
                if q_atype == "P0":
                    detail = {
                        "valid": True,
                        "dept_sub_name": "",
                        "step_id": "",
                        "project_status": "",
                        "project_status_raw": "",
                        "announce_type": "P0",
                    }
                    log(f"  📋 {jid}: P0 planning — save from RSS (no getProjectDetail)")
                else:
                    log(f"  ⚠️ {jid}: detail ไม่ valid — ข้าม (retry รอบหน้า)")
                    time.sleep(1)
                    continue

            # ── Winner fetch สำหรับ W0/contract stage (C/I/X) — มี winner data ใน getProcureResult ──
            step_id = detail.get("step_id", "")
            a_type  = detail.get("announce_type", "")
            if a_type == "W0" or step_id.startswith(("C", "I", "X")):
                winfo = get_procure_result(jid)
                if winfo.get("winner"):
                    price = winfo.get("winning_price", "")
                    budget = q_item.get("budget", "") or ""
                    pct = calc_pct_discount(budget, price)
                    cache[jid] = {
                        "winner_name":  winfo["winner"],
                        "winner_price": str(price),
                        "discount_pct": pct,
                        "award_date":   winfo.get("announce_date", ""),
                    }
                    new_winners += 1
                    detail["winner"] = cache[jid]  # ส่งต่อให้ _build_sparse_row ใส่ใน row

            sparse_row = _build_sparse_row(jid, q_item, detail)
            appended_rows.append(sparse_row)
            processed_pids.add(jid)
            log(f"  ✅ {jid}: sparse row prepared (step={detail.get('step_id')}, announce={detail.get('announce_type')}{', WINNER' if jid in cache else ''})")
            time.sleep(1)

    # ── Write ──
    if appended_rows:
        log(f"\nAppend {len(appended_rows)} sparse rows...")
        ws_all.append_rows(appended_rows, value_input_option="USER_ENTERED")
        log(f"  ✅ {len(appended_rows)} rows appended")

    # ── Remove processed from queue ──
    if args.from_queue:
        sheet_existing     = set(row_map.keys())
        processed_existing = sheet_existing & {q.get("projectId") for q in queue_items}
        remaining = [
            q for q in queue_items
            if q.get("projectId") not in processed_pids
            and q.get("projectId") not in processed_existing
        ]
        queue_file.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        removed = len(queue_items) - len(remaining)
        log(f"  📥 queue: removed {removed}, remaining {len(remaining)}")

    # ── Apply cell updates ──
    if update_payload:
        log(f"\nApply {len(update_payload)} row updates → all_jobs...")
        batch_data = []
        for u in update_payload:
            for field, val in u["fields"].items():
                if field in h_idx:
                    col = chr(ord("A") + h_idx[field])
                    batch_data.append({
                        "range":  f"all_jobs!{col}{u['row']}",
                        "values": [[val]],
                    })
        BATCH = 200
        for i in range(0, len(batch_data), BATCH):
            chunk = batch_data[i:i + BATCH]
            ws_all.spreadsheet.values_batch_update(
                {"valueInputOption": "USER_ENTERED", "data": chunk}
            )
        log(f"  applied {len(batch_data)} cell updates")

    if new_winners:
        save_winner_cache(cache)
        log(f"\n+{new_winners} winners → cache (รวม {len(cache)})")

    # ── Re-classify ──
    if update_payload or new_winners:
        log("\nเรียก Classifier rebuild...")
        try:
            from Sebastian_Classifier import main as classifier_main
            classifier_main()
        except Exception as e:
            log(f"  ⚠️ Classifier error: {e}")

    log(f"\n✅ สรุป:")
    log(f"  new winners:    {new_winners}")
    log(f"  status updates: {status_updates}")
    log(f"  cell updates:   {len(update_payload)}")
    log(f"  sparse inserts: {len(appended_rows)}")


if __name__ == "__main__":
    main()
