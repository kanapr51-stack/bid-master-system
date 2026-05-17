"""
Sebastian_Deploy_Dashboard.py
รัน `vercel deploy --prod` ใน dashboard/web เพื่อ deploy snapshot ล่าสุด

ใช้ใน pipeline หลัง snapshot.json ถูก generate:
    python scripts/Sebastian_Deploy_Dashboard.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    project_root = Path(__file__).parent.parent
    dashboard_dir = project_root / "dashboard" / "web"
    snapshot_file = dashboard_dir / "public" / "snapshot.json"

    if not dashboard_dir.exists():
        print(f"❌ ไม่พบ {dashboard_dir}")
        return 1
    if not snapshot_file.exists():
        print(f"❌ ไม่พบ {snapshot_file} — รัน snapshot generator ก่อน")
        return 1

    vercel = shutil.which("vercel")
    if not vercel:
        print("❌ ไม่พบ vercel CLI ใน PATH (npm i -g vercel)")
        return 1

    print(f"📦 Deploying dashboard ({snapshot_file.stat().st_size:,} bytes snapshot)…")
    try:
        result = subprocess.run(
            [vercel, "deploy", "--prod", "--yes"],
            cwd=str(dashboard_dir),
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("❌ Deploy timeout (>5 นาที)")
        return 1

    # Vercel CLI prints URL on stderr (interactive) and JSON-ish on stdout
    out = (result.stdout or "") + (result.stderr or "")
    # Find URL
    url = None
    for line in out.splitlines():
        line = line.strip()
        if "https://" in line and "vercel.app" in line:
            for tok in line.split():
                if tok.startswith("https://") and "vercel.app" in tok:
                    url = tok.rstrip(".,;)")
                    break
        if url:
            break

    if result.returncode == 0:
        print(f"✅ Deploy สำเร็จ" + (f" · {url}" if url else ""))
        return 0
    else:
        print(f"❌ Deploy fail (exit {result.returncode})")
        print(out[-1000:])
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
