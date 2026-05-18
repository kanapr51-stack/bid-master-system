"""
Sebastian_ETL_Sync.py — Periodic sync จาก Google Sheets → PostgreSQL

Wrapper รอบ etl_sheet_to_db.py + self-redirect log
ใช้กับ Windows Scheduled Task ทุก 30 นาที

Behavior:
  - UPSERT ทุก rows ใน 4 tables (idempotent — รันซ้ำได้ ไม่ duplicate)
  - บันทึก log แต่ละ run + summary
  - ถ้า ETL fail → log + exit non-zero (cron จะ alert)
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent


def _init_log_file():
    log_dir = os.environ.get("BMS_ETL_LOG_DIR", "").strip()
    if not log_dir:
        log_dir = str(ROOT / "logs" / "etl")
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        f = open(log_path / f"etl_{ts}.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    started = datetime.now()
    log("=" * 50)
    log("ETL Sync START")
    log("=" * 50)

    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "etl_sheet_to_db.py"), "--all"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.stdout:
            for line in result.stdout.splitlines():
                log(f"  {line}")
        if result.returncode != 0:
            log(f"❌ ETL fail (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.splitlines()[-10:]:
                    log(f"  stderr: {line}")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        log("❌ ETL timeout (>10 min)")
        sys.exit(1)

    elapsed = (datetime.now() - started).total_seconds()
    log(f"✅ ETL Sync DONE — {elapsed:.1f}s")


if __name__ == "__main__":
    _init_log_file()
    main()
