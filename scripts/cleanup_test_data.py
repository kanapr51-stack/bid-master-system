"""cleanup_test_data.py — ล้าง test data ที่ Sebastian_Customer_DB.py __main__ smoke test
insert ลง prod (รันตอน migrate N+119). กัญจน์ 2026-06-11.

test artifacts (hardcoded ใน __main__):
  - customer line_user_id='Uxxxxxxxxx_TEST' (+ subscription/provinces)
  - 4 fake project_ids → projects_seen + notification_queue (fan-out ถึงลูกค้าจริง!) + delivery_log
    69039196328, 69039000001, 69039999999, 69039000002

default = DRY-RUN (นับว่าจะลบอะไร ไม่ลบ). --apply = ลบจริง.
ปลอดภัย: discovery idempotent → ถ้า project จริงโดนลบ รอบ sweep หน้าเจอใหม่ (deadline gate ปกติ).

usage:
  python cleanup_test_data.py            # dry-run
  python cleanup_test_data.py --apply     # ลบจริง
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Customer_DB import get_connection

TEST_LINE_ID = "Uxxxxxxxxx_TEST"
FAKE_PROJECTS = ["69039196328", "69039000001", "69039999999", "69039000002"]


def _scalar(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else 0


def run(apply: bool = False) -> dict:
    ph = ",".join("?" for _ in FAKE_PROJECTS)
    with get_connection() as conn:
        cid_row = conn.execute("SELECT id FROM customers WHERE line_user_id=?",
                               (TEST_LINE_ID,)).fetchone()
        cid = cid_row[0] if cid_row else None

        print("=== cleanup test data — " + ("APPLY (ลบจริง)" if apply else "DRY-RUN (ไม่ลบ)") + " ===")
        print(f"test customer '{TEST_LINE_ID}': {'id='+str(cid) if cid else 'ไม่พบ'}")

        # queue ของงานปลอม — แยกตามสถานะ + ลูกค้าจริง vs ทดสอบ (สำคัญ: pending = ยังไม่ส่ง = เสี่ยง)
        print("\nงานปลอมในคิว (notification_queue):")
        for pj in FAKE_PROJECTS:
            tot = _scalar(conn, "SELECT COUNT(*) FROM notification_queue WHERE project_id=?", (pj,))
            pend = _scalar(conn, "SELECT COUNT(*) FROM notification_queue WHERE project_id=? "
                                 "AND status IN ('pending','sending')", (pj,))
            # งานนี้เป็นของจริงไหม? (มี enrichment location = discovery จริงเคยแตะ)
            real = _scalar(conn, "SELECT COUNT(*) FROM project_locations WHERE project_id=? "
                                 "AND enrichment_status='enriched'", (pj,))
            flag = " ⚠️PENDING(เสี่ยงส่ง)" if pend else ""
            hint = " [มี enrich จริง]" if real else ""
            print(f"  {pj}: queue={tot} (pending={pend}){flag}{hint}")

        # นับสิ่งที่จะลบ
        counts = {
            "queue_fake": _scalar(conn, f"SELECT COUNT(*) FROM notification_queue WHERE project_id IN ({ph})", FAKE_PROJECTS),
            "queue_cust": _scalar(conn, "SELECT COUNT(*) FROM notification_queue WHERE customer_id=?", (cid,)) if cid else 0,
            "deliv_fake": _scalar(conn, f"SELECT COUNT(*) FROM delivery_log WHERE project_id IN ({ph})", FAKE_PROJECTS),
            "projseen": _scalar(conn, f"SELECT COUNT(*) FROM projects_seen WHERE project_id IN ({ph})", FAKE_PROJECTS),
            "predictions": _scalar(conn, f"SELECT COUNT(*) FROM price_predictions WHERE project_id IN ({ph})", FAKE_PROJECTS),
            "subs": _scalar(conn, "SELECT COUNT(*) FROM subscriptions WHERE customer_id=?", (cid,)) if cid else 0,
            "follows": _scalar(conn, "SELECT COUNT(*) FROM followed_jobs WHERE customer_id=?", (cid,)) if cid else 0,
        }
        print("\nจะลบ:")
        print(f"  notification_queue: งานปลอม {counts['queue_fake']} + ของ test customer {counts['queue_cust']}")
        print(f"  delivery_log (งานปลอม): {counts['deliv_fake']}")
        print(f"  projects_seen (งานปลอม): {counts['projseen']}")
        print(f"  price_predictions (งานปลอม): {counts['predictions']}")
        print(f"  test customer: subs={counts['subs']} follows={counts['follows']} + customer row")

        if not apply:
            print("\nℹ️ DRY-RUN — ยังไม่ลบ (ใส่ --apply เพื่อลบจริง)")
            return counts

        # ลบจริง — ลูกก่อนพ่อ (FK-safe)
        conn.execute(f"DELETE FROM notification_queue WHERE project_id IN ({ph})", FAKE_PROJECTS)
        conn.execute(f"DELETE FROM delivery_log WHERE project_id IN ({ph})", FAKE_PROJECTS)
        conn.execute(f"DELETE FROM projects_seen WHERE project_id IN ({ph})", FAKE_PROJECTS)
        conn.execute(f"DELETE FROM project_locations WHERE project_id IN ({ph})", FAKE_PROJECTS)
        conn.execute(f"DELETE FROM price_predictions WHERE project_id IN ({ph})", FAKE_PROJECTS)
        if cid:
            conn.execute("DELETE FROM notification_queue WHERE customer_id=?", (cid,))
            conn.execute("DELETE FROM delivery_log WHERE customer_id=?", (cid,))
            conn.execute("DELETE FROM followed_jobs WHERE customer_id=?", (cid,))
            conn.execute("DELETE FROM subscription_provinces WHERE subscription_id IN "
                         "(SELECT id FROM subscriptions WHERE customer_id=?)", (cid,))
            conn.execute("DELETE FROM subscriptions WHERE customer_id=?", (cid,))
            conn.execute("DELETE FROM customers WHERE id=?", (cid,))
        conn.commit()
        print("\n✅ ลบ test data เรียบร้อย")
        return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ลบจริง (default = dry-run)")
    a = ap.parse_args()
    run(apply=a.apply)


if __name__ == "__main__":
    main()
