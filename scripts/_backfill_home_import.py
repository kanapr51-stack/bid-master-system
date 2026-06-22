"""ONE-OFF (temp): import data/_backfill_home/backfill_results.json เข้า bid_results.
{pid: {"bidders":[...], "announce_date": str}} → record_bid_results(pid, bidders, fetched_at=announce_date).
รันบน VPS เท่านั้น (ต้องชี้ BMS_DATA_DIR ไปหา bms_customers.db จริง). idempotent (record_bid_results = INSERT OR REPLACE)
→ รันซ้ำได้ปลอดภัยถ้าโดน interrupt กลางทาง. checkpoint ทุก CHECKPOINT_EVERY ด้วย seen-set กันงานที่ stored แล้วโดนเขียนซ้ำเปล่าๆ."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import SubscriptionStore

IN_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/_backfill_home/backfill_results.json"
SEEN_PATH = IN_PATH + ".imported_seen.json"
CHECKPOINT_EVERY = 200


def load_seen():
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    tmp = SEEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)
    os.replace(tmp, SEEN_PATH)


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    seen = load_seen()
    todo = [(pid, rec) for pid, rec in data.items() if pid not in seen and rec.get("bidders")]
    print(f"total={len(data)} already_imported={len(seen)} todo={len(todo)}")
    store = SubscriptionStore()
    stats = {"stored": 0, "rows": 0}
    t0 = time.time()
    for i, (pid, rec) in enumerate(todo, 1):
        n = store.record_bid_results(pid, rec["bidders"], fetched_at=rec.get("announce_date") or None)
        stats["stored"] += 1
        stats["rows"] += n
        seen.add(pid)
        if i % CHECKPOINT_EVERY == 0:
            save_seen(seen)
            el = time.time() - t0
            eta = el / i * (len(todo) - i)
            print(f"  [{i}/{len(todo)}] stored={stats['stored']} rows={stats['rows']} "
                  f"| {el:.0f}s, ETA ~{eta:.0f}s")
    save_seen(seen)
    print(f"DONE: stored_projects={stats['stored']} bid_rows={stats['rows']}")


if __name__ == "__main__":
    main()
