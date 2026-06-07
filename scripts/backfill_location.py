"""backfill_location.py — เติม raw location (district_moi_id/moi_name/lat-lng) ให้งานเป้าหมายที่
ยังเปิด + ยังไม่มี location. low-rate (INC-001). รันบนเครื่องที่ยิง API ได้.

SAFE BY DEFAULT: dry-run เป็น default (แค่ดู candidate) — ต้อง --execute ถึงยิง API จริง.
รอบแรก deploy: --limit ≤ 20 (conservative rollout)."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection, save_project_location_raw
from process5_http_client import get_procurement_detail

SLEEP = 2.5   # INC-001 throughput envelope (≥2s ต่อ call)


def _candidates(limit: int):
    with get_connection() as conn:
        return [r[0] for r in conn.execute("""
            SELECT project_id FROM project_locations
            WHERE (district_moi_id IS NULL OR district_moi_id='')
              AND (latitude IS NULL OR latitude='')
              AND qualification_status IN ('enqueued', 'suppressed_preview')
            LIMIT ?""", (limit,)).fetchall()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="ยิง API จริง (default = dry-run)")
    ap.add_argument("--limit", type=int, default=20, help="จำนวนงานสูงสุด (default 20, conservative)")
    a = ap.parse_args(argv)
    ids = _candidates(a.limit)
    print(f"candidates (active+no-location): {len(ids)} (limit {a.limit})")
    if not a.execute:
        print("DRY-RUN (default) — ใส่ --execute เพื่อยิงจริง")
        for pid in ids[:20]:
            print(f"  would backfill: {pid}")
        return 0
    ok = 0
    for i, pid in enumerate(ids):
        try:
            d = get_procurement_detail(pid)
            if d.get("valid") and (d.get("district_moi_id") or d.get("latitude")):
                save_project_location_raw(pid, d.get("district_moi_id") or "", d.get("moi_name") or "",
                                          d.get("latitude") or "", d.get("longitude") or "")
                ok += 1
                print(f"  [{i+1}/{len(ids)}] OK {pid} moi={d.get('moi_name')} "
                      f"has_coord={bool(d.get('latitude'))}")
            else:
                print(f"  [{i+1}/{len(ids)}] SKIP {pid} (no location in API)")
        except Exception as e:
            print(f"  [{i+1}/{len(ids)}] ERR {pid}: {e}")
        time.sleep(SLEEP)
    print(f"✅ backfilled {ok}/{len(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
