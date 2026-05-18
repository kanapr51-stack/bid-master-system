"""
Sebastian_Dashboard_Refresh.py — Regenerate snapshot + upload to Vercel Blob
ใช้สำหรับ cron 30 นาที ระหว่าง gentle scan/อื่นๆ ทำงานเพื่อให้ Dashboard fresh

Steps:
  1. รัน dashboard_extractor.py → regenerate snapshot.json
  2. รัน Sebastian_Upload_Snapshot.py → POST ไป Vercel Blob + revalidate
"""
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent


def _init_log_file():
    """Self-redirect stdout/stderr to rotating log file"""
    log_dir = os.environ.get("BMS_DASHBOARD_LOG_DIR", "").strip()
    if not log_dir:
        log_dir = str(ROOT / "logs" / "dashboard")
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        f = open(log_path / f"refresh_{ts}.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_step(name: str, script: str) -> bool:
    log(f"→ {name}")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.stdout:
            for line in result.stdout.splitlines()[-3:]:
                log(f"    {line}")
        if result.returncode != 0:
            log(f"   ❌ exit {result.returncode}")
            if result.stderr:
                for line in result.stderr.splitlines()[-3:]:
                    log(f"    err: {line}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"   ❌ timeout")
        return False
    except Exception as e:
        log(f"   ❌ {e}")
        return False


def main():
    started = datetime.now()
    log("=" * 50)
    log(f"Dashboard Refresh START")
    log("=" * 50)

    ok_extract = run_step("Extract snapshot", "dashboard_extractor.py")
    if not ok_extract:
        log("Extract failed → ข้าม upload")
        sys.exit(1)

    ok_upload = run_step("Upload to Blob + revalidate", "Sebastian_Upload_Snapshot.py")
    if not ok_upload:
        log("Upload failed")
        sys.exit(2)

    elapsed = (datetime.now() - started).total_seconds()
    log(f"✅ DONE in {elapsed:.1f}s")


if __name__ == "__main__":
    _init_log_file()
    main()
