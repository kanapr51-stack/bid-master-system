"""ONE-OFF (temp): fetch full-bidder lists จากเน็ตบ้าน (residential) — workaround WAF block VPS.

อ่าน candidates JSON (จาก VPS select_candidates) → get_procure_result ทีละงาน
→ dump {project_id: {"bidders": [...], "announce_date": str}} ลง results JSON (resumable)
→ scp results กลับ VPS → import ผ่าน record_bid_results (storage path เดิมที่ test แล้ว)

ไม่แตะ DB local. fail-open: error = ไม่บันทึก (retry รอบหน้า). empty = บันทึก {} กัน refetch.
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from process5_http_client import get_procure_result

CANDS = sys.argv[1] if len(sys.argv) > 1 else "data/_backfill_home/backfill_cands.json"
OUT   = sys.argv[2] if len(sys.argv) > 2 else "data/_backfill_home/backfill_results.json"
SLEEP = 1.5
COOLDOWN_EVERY = 50
COOLDOWN_SEC = 60
CHECKPOINT_EVERY = 25


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_out(d):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, OUT)


def main():
    cands = load_json(CANDS, [])
    out = load_json(OUT, {})              # {pid: {"bidders":[...], "announce_date":str}}
    todo = [(pid, ad) for pid, ad in cands if pid not in out]
    print(f"candidates={len(cands)} done={len(out)} todo={len(todo)}")
    stats = {"stored": 0, "empty": 0, "error": 0}
    t0 = time.time()
    for i, (pid, ad) in enumerate(todo, 1):
        try:
            res = get_procure_result(pid)
        except Exception as e:
            print(f"  {pid} fetch FAIL: {type(e).__name__}")
            stats["error"] += 1
            res = None
        if res is None or "bidders" not in res:
            stats["error"] += 1            # ไม่บันทึก → retry รอบหน้า
        else:
            bidders = res["bidders"]
            out[pid] = {"bidders": bidders, "announce_date": ad}
            stats["empty" if not bidders else "stored"] += 1
        if i % CHECKPOINT_EVERY == 0:
            save_out(out)
            el = time.time() - t0
            eta = el / i * (len(todo) - i)
            print(f"  [{i}/{len(todo)}] stored={stats['stored']} empty={stats['empty']} "
                  f"error={stats['error']} | {el:.0f}s, ETA ~{eta/60:.0f}m")
        if COOLDOWN_EVERY and i % COOLDOWN_EVERY == 0 and i < len(todo):
            save_out(out)
            print(f"  cooldown {COOLDOWN_SEC}s")
            time.sleep(COOLDOWN_SEC)
        else:
            time.sleep(SLEEP)
    save_out(out)
    print(f"DONE: stored={stats['stored']} empty={stats['empty']} error={stats['error']} "
          f"| total_in_results={len(out)}")


if __name__ == "__main__":
    main()
