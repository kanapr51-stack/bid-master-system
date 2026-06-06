"""cgd_sync_to_vps.py — extract subset เป้าหมายจาก winner_history.db → scp → VPS merge.

2 ฝั่ง:
- residential (เครื่องบ้าน): `python cgd_sync_to_vps.py --push`
  extract_subset(winner_history.db) → เขียน cgd_subset.jsonl → scp → ssh ให้ VPS merge
- VPS: `... cgd_sync_to_vps.py --merge-from /opt/bms/data/cgd_subset.jsonl`
  อ่าน jsonl → merge_winners() upsert cgd_winners (idempotent)

merge_winners()/get_cgd_winners() ใช้ Sebastian_Customer_DB (bms_customers.db ฝั่ง VPS).
extract_subset() อ่าน winner_history.db (ฝั่ง residential).
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from Sebastian_Customer_DB import get_connection, _now

TARGET = ["นครพนม", "บึงกาฬ"]

VPS_HOST = os.environ.get("VPS_HOST", "root@45.76.156.166")
VPS_KEY = os.path.expanduser(os.environ.get("VPS_KEY", "~/.ssh/bms_vps"))
REMOTE_DATA = os.environ.get("BMS_REMOTE_DATA", "/opt/bms/data")
REMOTE_PY = os.environ.get("BMS_REMOTE_PY", "/opt/bms/venv/bin/python")
REMOTE_APP = os.environ.get("BMS_REMOTE_APP", "/opt/bms/app")


def merge_winners(rows: list, now: str = None) -> int:
    """upsert cgd_winners (idempotent ตาม project_id). ใช้ทั้งฝั่ง VPS รับ + test."""
    now = now or _now()
    n = 0
    with get_connection() as conn:
        for r in rows:
            conn.execute("""INSERT OR REPLACE INTO cgd_winners
                (project_id, province, dept, project_name, winner, winner_tin, budget,
                 win_price, discount_pct, announce_date, fiscal_year, synced_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["project_id"], r.get("province"), r.get("dept"), r.get("project_name"),
                 r.get("winner"), r.get("winner_tin"), r.get("budget"), r.get("win_price"),
                 r.get("discount_pct"), r.get("announce_date"), r.get("fiscal_year"), now))
            n += 1
    return n


def get_cgd_winners(province: str) -> list[dict]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cgd_winners WHERE province=? ORDER BY announce_date DESC", (province,))]


def extract_subset(wh_db_path: str, provinces=TARGET) -> list[dict]:
    """ดึง subset เป้าหมายจาก winner_history (residential node) เป็น list[dict] เพื่อส่ง VPS."""
    conn = sqlite3.connect(wh_db_path)
    conn.row_factory = sqlite3.Row
    qs = ",".join("?" * len(provinces))
    rows = [dict(r) for r in conn.execute(
        f"SELECT project_id, province, dept, project_name, winner, winner_tin, budget, "
        f"win_price, discount_pct, announce_date, fiscal_year FROM winner_history "
        f"WHERE province IN ({qs})", provinces)]
    conn.close()
    return rows


# ── orchestration (Task 2.3) ────────────────────────────────────────────────

def _merge_from_jsonl(path: str) -> int:
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    n = merge_winners(rows)
    print(f"✅ merge {n} cgd_winners เข้า bms_customers.db")
    return n


def push(wh_db_path: str = None, provinces=TARGET) -> int:
    """residential: extract → jsonl → scp → ssh merge บน VPS."""
    wh_db_path = wh_db_path or str(Path(__file__).parent.parent / "data" / "winner_history.db")
    subset = extract_subset(wh_db_path, provinces)
    out = Path(__file__).parent.parent / "data" / "cgd_subset.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in subset:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"extract {len(subset)} row ({','.join(provinces)}) → {out.name}")
    if not shutil.which("scp"):
        print("❌ ไม่เจอ scp ใน PATH"); return 1
    remote_jsonl = f"{REMOTE_DATA}/cgd_subset.jsonl"
    scp = ["scp", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=15", str(out), f"{VPS_HOST}:{remote_jsonl}"]
    r = subprocess.run(scp, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"❌ scp ล้มเหลว (rc={r.returncode}): {r.stderr.strip()[:200]}"); return 2
    print(f"✅ scp → {VPS_HOST}:{remote_jsonl}")
    remote_cmd = (f"sudo -u bms BMS_DATA_DIR={REMOTE_DATA} {REMOTE_PY} "
                  f"{REMOTE_APP}/scripts/cgd_sync_to_vps.py --merge-from {remote_jsonl}")
    ssh = ["ssh", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ConnectTimeout=20", VPS_HOST, remote_cmd]
    r2 = subprocess.run(ssh, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    print((r2.stdout or "").strip())
    if r2.returncode != 0:
        print(f"❌ ssh merge ล้มเหลว (rc={r2.returncode}): {r2.stderr.strip()[:200]}"); return 3
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-from", help="(VPS) อ่าน jsonl → merge cgd_winners")
    ap.add_argument("--push", action="store_true", help="(residential) extract→scp→VPS merge")
    a = ap.parse_args(argv)
    if a.merge_from:
        from Sebastian_Customer_DB import init_schema
        init_schema()                      # ensure cgd_winners (v119) มีบน VPS
        return 0 if _merge_from_jsonl(a.merge_from) >= 0 else 1
    if a.push:
        return push()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
