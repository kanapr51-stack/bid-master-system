"""
heal_winner_cache.py — ลบ entries ที่ winner_name='province:...'/'keyword:...' (raw qn)
ออกจาก winner_cache_bootstrap.json + แสดง bad jids เพื่อ refresh ต่อ
"""
import sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

CACHE = Path(__file__).parent.parent / "data" / "winner_cache_bootstrap.json"
BACKUP = Path(__file__).parent.parent / "data" / f"winner_cache_pre_heal.json"

cache = json.loads(CACHE.read_text(encoding="utf-8"))
bad_jids = [jid for jid, info in cache.items() if str(info.get("winner_name","")).startswith(("province:","keyword:"))]

print(f"Total: {len(cache)}, bad: {len(bad_jids)}")
if not bad_jids:
    print("ไม่มีอะไรต้องลบ")
    sys.exit(0)

# Backup
BACKUP.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backup → {BACKUP.name}")

# Remove bad
for jid in bad_jids:
    del cache[jid]
CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ลบ {len(bad_jids)} bad → cache เหลือ {len(cache)}")

# Print jids for refresh
print("\nBad jids (สำหรับ refresh):")
print(",".join(bad_jids))
