"""
Sebastian_Upload_Snapshot.py
อัปโหลด snapshot.json ไป Vercel Blob ผ่าน /api/snapshot endpoint
แล้ว trigger revalidate ของ dashboard pages → instant update (< 5s)

ใช้แทน Sebastian_Deploy_Dashboard.py สำหรับ real-time mode:
    python scripts/Sebastian_Upload_Snapshot.py

ความต่าง:
    Deploy script:  rebuild dashboard ใหม่ทั้งหมด (~1 นาที)
    Upload script:  ส่ง snapshot ใหม่ → revalidate (~3-5 วินาที)
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


def upload(snapshot_path: Path) -> bool:
    base = os.environ.get("VERCEL_DASHBOARD_URL", "").strip().rstrip("/")
    secret = os.environ.get("REVALIDATE_SECRET", "").strip()
    if not base or not secret:
        print("❌ VERCEL_DASHBOARD_URL / REVALIDATE_SECRET ไม่ตั้งใน .env")
        return False
    if not snapshot_path.exists():
        print(f"❌ ไม่พบ {snapshot_path}")
        return False

    body = snapshot_path.read_bytes()
    url = f"{base}/api/snapshot"
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            blob_info = data.get("blob", {})
            paths = data.get("revalidated", [])
            print(
                f"✅ Uploaded {blob_info.get('size', 0):,} bytes → "
                f"{blob_info.get('pathname', '?')} · revalidated {len(paths)} pages"
            )
            return True
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"❌ Upload failed (HTTP {e.code}): {msg}")
        return False
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return False


if __name__ == "__main__":
    load_env()
    root = Path(__file__).parent.parent
    snapshot = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else root / "dashboard" / "web" / "public" / "snapshot.json"
    )
    ok = upload(snapshot)
    sys.exit(0 if ok else 1)
