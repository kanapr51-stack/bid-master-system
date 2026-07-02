"""test_clear_keyword_seed.py — เคลียร์ 89-keyword seed ออกจาก customers.notes (idempotent)."""
import os, tempfile, sys, json
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db   # noqa: E402
db.init_schema()
import clear_keyword_seed as cks      # noqa: E402


def test_clears_classes_key():
    s = db.SubscriptionStore()
    cid = s.add_customer("Uaa", "กัญจน์")
    seeded = json.dumps({"classes": [{"keywords": ["ก่อสร้าง"] * 89}], "other": 1})
    with db.get_connection() as conn:
        conn.execute("UPDATE customers SET notes=? WHERE id=?", (seeded, cid))
        n = cks.clear_keyword_seed(conn)
        assert n == 1, n
        notes = conn.execute("SELECT notes FROM customers WHERE id=?", (cid,)).fetchone()[0]
    parsed = json.loads(notes)
    assert "classes" not in parsed or parsed["classes"] == [], parsed
    assert parsed.get("other") == 1, "ต้องไม่แตะ key อื่น"
    # idempotent — รันซ้ำ = 0 แถว
    with db.get_connection() as conn:
        assert cks.clear_keyword_seed(conn) == 0
    print("✅ clear_keyword_seed — เคลียร์ classes, คง key อื่น, idempotent")


test_clears_classes_key()
print("ALL PASS clear_keyword_seed")
