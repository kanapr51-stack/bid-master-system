"""
Sebastian_Revalidate_Dashboard.py
ส่ง POST ไป /api/revalidate ของ Vercel dashboard เพื่อให้หน้า refresh ทันที
หลังจาก snapshot.json เปลี่ยน

ใช้ใน pipeline หลังจาก step ที่ generate snapshot เสร็จ:
    python scripts/Sebastian_Revalidate_Dashboard.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


def revalidate(path: str = "/") -> bool:
    base = os.environ.get("VERCEL_DASHBOARD_URL", "").strip().rstrip("/")
    secret = os.environ.get("REVALIDATE_SECRET", "").strip()
    if not base or not secret:
        print("⚠️  VERCEL_DASHBOARD_URL / REVALIDATE_SECRET ไม่ตั้งใน .env — ข้าม revalidate")
        return False

    url = f"{base}/api/revalidate"
    body = json.dumps({"path": path}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-revalidate-secret": secret,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            paths = data.get("revalidated", [])
            print(f"✅ Dashboard revalidated: {', '.join(paths)}")
            return True
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"❌ Revalidate failed (HTTP {e.code}): {msg}")
        return False
    except Exception as e:
        print(f"❌ Revalidate error: {e}")
        return False


if __name__ == "__main__":
    load_env()
    path = sys.argv[1] if len(sys.argv) > 1 else "/"
    ok = revalidate(path)
    sys.exit(0 if ok else 1)
