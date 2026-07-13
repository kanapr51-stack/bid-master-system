"""webpush_send: ส่งสำเร็จ→log sent+last_ok_at · 410→disable · exception→ไม่ raise · kill switch · split_text"""
import os, sys, tempfile, types
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  VAPID_PRIVATE_KEY="testpriv", VAPID_SUBJECT="mailto:t@t.co")
os.environ.pop("BMS_WEBPUSH_DISABLED", None)
sys.path.insert(0, str(Path(__file__).parent))

# fake pywebpush ก่อน import module (ห้ามยิงเน็ตจริงใน test)
fake = types.ModuleType("pywebpush")
class WebPushException(Exception):
    def __init__(self, msg, response=None):
        super().__init__(msg); self.response = response
CALLS = []
def _webpush_ok(**kw): CALLS.append(kw); return True
fake.webpush = _webpush_ok
fake.WebPushException = WebPushException
sys.modules["pywebpush"] = fake

import Sebastian_Customer_DB as db
db.init_schema()
import webpush_send as wp

NOW = "2026-07-14T00:00:00+07:00"
with db.get_connection() as conn:
    conn.execute("INSERT INTO customers (line_user_id, display_name, tier, created_at, updated_at) "
                 "VALUES ('UPUSH','x','trial',?,?)", (NOW, NOW))
    cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UPUSH'").fetchone()["id"]
    conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                 "VALUES (?, 'https://push.example/ep1', 'pk', 'ak', ?)", (cid, NOW))

# 1) success → log sent + last_ok_at + payload ครบ
sent, failed = wp.send_to_user("UPUSH", "หัวข้อ", "เนื้อหา", "https://board/x", "P1", "api_enriched")
assert (sent, failed) == (1, 0), (sent, failed)
assert CALLS and CALLS[0]["subscription_info"]["endpoint"] == "https://push.example/ep1"
import json
payload = json.loads(CALLS[0]["data"])
assert payload == {"title": "หัวข้อ", "body": "เนื้อหา", "url": "https://board/x"}, payload
with db.get_connection() as conn:
    row = conn.execute("SELECT status, project_id, source_stage FROM webpush_delivery_log").fetchone()
    assert (row["status"], row["project_id"], row["source_stage"]) == ("sent", "P1", "api_enriched"), dict(row)
    assert conn.execute("SELECT last_ok_at FROM push_subscriptions").fetchone()["last_ok_at"]

# 2) 410 Gone → disabled_at + log failed
class _Resp: status_code = 410
def _webpush_410(**kw): raise WebPushException("gone", response=_Resp())
fake.webpush = _webpush_410
sent, failed = wp.send_to_user("UPUSH", "t", "b", "u")
assert (sent, failed) == (0, 1), (sent, failed)
with db.get_connection() as conn:
    assert conn.execute("SELECT disabled_at FROM push_subscriptions").fetchone()["disabled_at"]
    # เครื่องถูก disable แล้ว → ส่งรอบถัดไปไม่ยิงซ้ำ
sent, failed = wp.send_to_user("UPUSH", "t", "b", "u")
assert (sent, failed) == (0, 0), (sent, failed)

# 3) exception แปลกๆ → ไม่ raise
with db.get_connection() as conn:
    conn.execute("UPDATE push_subscriptions SET disabled_at=NULL")
def _webpush_boom(**kw): raise RuntimeError("boom")
fake.webpush = _webpush_boom
sent, failed = wp.mirror_text("UPUSH", "บรรทัดแรก\nบรรทัดสอง", "P2", "followed_winner")
assert (sent, failed) == (0, 1), (sent, failed)

# 4) kill switch
os.environ["BMS_WEBPUSH_DISABLED"] = "1"
assert wp.send_to_user("UPUSH", "t", "b", "u") == (0, 0)
os.environ.pop("BMS_WEBPUSH_DISABLED")

# 5) split_text + job_url
assert wp.split_text("🏗️ งานใหม่ ก่อสร้างถนน\nจังหวัด นครพนม\nงบ 1,000,000") == \
    ("🏗️ งานใหม่ ก่อสร้างถนน", "จังหวัด นครพนม งบ 1,000,000")
assert wp.job_url("P9").endswith("/portal/job/P9")
assert wp.job_url("").endswith("/portal/world")

print("PASS test_webpush_send")
