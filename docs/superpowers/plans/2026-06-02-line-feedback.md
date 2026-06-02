# LINE Feedback Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ให้ user กดปุ่ม feedback (สนใจ/เกี่ยวข้องแต่ไม่น่าสนใจ/ไม่เกี่ยวข้อง) บนงานที่ส่งทาง LINE → เก็บ feedback table (project_id ตรง) → รายงานกัญจน์

**Architecture:** LINE_Sender ส่งงานเป็น flex message + 3 ปุ่ม postback (data=`fb:<action>:<project_id>`) → bms_api `/webhook/line` มี postback handler → parse → เก็บ feedback table + reply ขอบคุณ → Daily_Digest สรุป. ต่อยอด existing text-feedback (ไม่ลบ)

**Tech Stack:** Python, FastAPI (bms_api), LINE Messaging API (flex message + postback), SQLite (feedback table — มีอยู่แล้ว)

**Test approach:** BMS ไม่มี pytest framework → pure functions ใช้ inline assert (`python -c`), integration verify ด้วยการ deploy + curl webhook จริง

---

## File Structure
| ไฟล์ | responsibility | สถานะ |
|---|---|---|
| `scripts/Sebastian_LINE_Sender.py` | สร้าง flex message + ปุ่ม postback + ส่ง | modify |
| `scripts/bms_api.py` | postback event handler → เก็บ feedback + reply | modify (เพิ่ม handler) |
| `scripts/Sebastian_Daily_Digest.py` | สรุป feedback ให้กัญจน์ | modify (เพิ่ม section) |
| `feedback` table | เก็บ feedback | มีอยู่แล้ว (ไม่แตะ schema) |

**Action values (คงที่ทั้งระบบ):** `interested` (👍) · `relevant_low` (🤔) · `irrelevant` (👎)
**Postback data format:** `fb:<action>:<project_id>` เช่น `fb:interested:69059297571`

---

## Task 1: Postback data helpers (parse + build) — pure functions

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่ม helpers ใกล้ต้นไฟล์ หลัง constants)

- [ ] **Step 1: เขียน inline test (parse + build round-trip)**

สร้างไฟล์ชั่วคราว `scripts/_test_fb.py`:
```python
import sys; sys.path.insert(0, "scripts")
from Sebastian_LINE_Sender import build_postback_data, parse_postback_data, FB_ACTIONS

# build
assert build_postback_data("interested", "69059297571") == "fb:interested:69059297571"
# parse round-trip
assert parse_postback_data("fb:interested:69059297571") == ("interested", "69059297571")
# parse invalid
assert parse_postback_data("hello") is None
assert parse_postback_data("fb:badaction:123") is None   # action ไม่อยู่ใน FB_ACTIONS
# parse project ที่มี : ไม่ได้ (project_id เป็นตัวเลขล้วน — split maxsplit=2)
assert parse_postback_data("fb:irrelevant:6905") == ("irrelevant", "6905")
print("PASS task1")
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python scripts/_test_fb.py`
Expected: FAIL (`ImportError: cannot import name 'build_postback_data'`)

- [ ] **Step 3: เพิ่ม helpers ใน Sebastian_LINE_Sender.py**

หลัง `TYPE_LABELS = {...}` (ราว line 44) เพิ่ม:
```python
# ── Feedback postback (P2 — ปุ่มกดใน LINE) ──────────────────────────────────
# action labels (ตรงกับ feedback table + bms_api postback handler)
FB_ACTIONS = {
    "interested":   "👍 สนใจ/น่าติดตาม",
    "relevant_low": "🤔 เกี่ยวข้องแต่ไม่น่าสนใจ",
    "irrelevant":   "👎 ไม่เกี่ยวข้องเลย",
}


def build_postback_data(action: str, project_id: str) -> str:
    """สร้าง postback data string: fb:<action>:<project_id>"""
    return f"fb:{action}:{project_id}"


def parse_postback_data(data: str):
    """parse 'fb:<action>:<project_id>' → (action, project_id) | None ถ้าผิดรูปแบบ"""
    if not data or not data.startswith("fb:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    _, action, project_id = parts
    if action not in FB_ACTIONS or not project_id:
        return None
    return action, project_id
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python scripts/_test_fb.py`
Expected: `PASS task1`

- [ ] **Step 5: ลบไฟล์ test ชั่วคราว + commit**

```bash
rm scripts/_test_fb.py
git add scripts/Sebastian_LINE_Sender.py
git commit -m "feat(line): postback data helpers (build/parse fb:action:project)"
```

---

## Task 2: Flex message builder (งาน + 3 ปุ่ม postback)

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่ม `build_job_flex` หลัง helpers Task 1)

- [ ] **Step 1: เขียน inline test (flex structure + ปุ่มครบ 3)**

สร้าง `scripts/_test_flex.py`:
```python
import sys; sys.path.insert(0, "scripts")
from Sebastian_LINE_Sender import build_job_flex

flex = build_job_flex(project_id="69059297571", title="ก่อสร้างถนน คสล. ต.โพธิ์หมากแข้ง",
                      detail="💰 4.5 ล้านบาท · ⏳ ยื่นซอง 8 มิ.ย.")
assert flex["type"] == "bubble"
# footer มี 3 ปุ่ม postback
btns = flex["footer"]["contents"]
assert len(btns) == 3
datas = [b["action"]["data"] for b in btns]
assert "fb:interested:69059297571" in datas
assert "fb:relevant_low:69059297571" in datas
assert "fb:irrelevant:69059297571" in datas
assert all(b["action"]["type"] == "postback" for b in btns)
print("PASS task2")
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python scripts/_test_flex.py`
Expected: FAIL (`ImportError: cannot import name 'build_job_flex'`)

- [ ] **Step 3: เพิ่ม `build_job_flex` ใน Sebastian_LINE_Sender.py**

หลัง `parse_postback_data` เพิ่ม:
```python
def build_job_flex(project_id: str, title: str, detail: str, doc_url: str = "") -> dict:
    """สร้าง flex bubble: งาน (body) + 3 ปุ่ม feedback postback (footer).
    คืน contents dict (ใส่ใน message type=flex)"""
    body_contents = [
        {"type": "text", "text": "🏗️ " + title[:160], "wrap": True, "weight": "bold", "size": "sm"},
        {"type": "text", "text": detail[:120], "wrap": True, "size": "xs", "color": "#666666", "margin": "md"},
    ]
    if doc_url:
        body_contents.append({
            "type": "button", "style": "link", "height": "sm", "margin": "md",
            "action": {"type": "uri", "label": "📎 ดูเอกสาร", "uri": doc_url},
        })
    footer_btns = []
    for action, label in FB_ACTIONS.items():
        footer_btns.append({
            "type": "button", "style": "secondary", "height": "sm",
            "action": {"type": "postback", "label": label,
                       "data": build_postback_data(action, project_id),
                       "displayText": label},
        })
    return {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "contents": body_contents},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer_btns},
    }
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python scripts/_test_flex.py`
Expected: `PASS task2`

- [ ] **Step 5: ลบ test + commit**

```bash
rm scripts/_test_flex.py
git add scripts/Sebastian_LINE_Sender.py
git commit -m "feat(line): build_job_flex — flex message + 3 feedback postback buttons"
```

---

## Task 3: ส่ง flex (เพิ่ม send_line_flex + ใช้ตอนส่งงาน)

**Files:**
- Modify: `scripts/Sebastian_LINE_Sender.py` (เพิ่ม `send_line_flex` + จุดที่ส่งงานใช้ flex)

- [ ] **Step 1: เพิ่ม `send_line_flex` (คู่ขนาน send_line_push)**

หลัง `send_line_push` (ราว line 230) เพิ่ม:
```python
def send_line_flex(token: str, line_user_id: str, alt_text: str,
                   flex_contents: dict) -> tuple[bool, str, str]:
    """ส่ง flex message. Returns (success, error_type, error_msg). โครงเดียวกับ send_line_push"""
    try:
        r = req_lib.post(
            LINE_PUSH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"to": line_user_id,
                  "messages": [{"type": "flex", "altText": alt_text[:400], "contents": flex_contents}]},
            timeout=10,
        )
        if r.status_code == 200:
            return True, "", ""
        try:
            detail = r.json().get("message", r.text[:120])
        except Exception:
            detail = r.text[:120]
        if r.status_code == 429:
            return False, "retryable", f"HTTP 429 rate_limit: {detail}"
        if r.status_code >= 500:
            return False, "retryable", f"HTTP {r.status_code}: {detail}"
        return False, "terminal", f"HTTP {r.status_code}: {detail}"
    except req_lib.Timeout:
        return False, "retryable", "timeout"
    except Exception as e:
        return False, "retryable", f"{type(e).__name__}: {e}"
```

- [ ] **Step 2: หาจุดที่ส่งงาน (send_line_push) ใน main()**

Run: `grep -n "send_line_push(token" scripts/Sebastian_LINE_Sender.py`
อ่าน context รอบบรรทัดนั้น (จุดที่ส่ง notification งานให้ user — มี `text` + `item` ที่มี project_id)

- [ ] **Step 3: เปลี่ยนจุดส่งงานให้ใช้ flex (เก็บ text เป็น altText)**

ที่จุดส่ง (หลัง build `text` ของงาน) — แทน `send_line_push(token, line_user_id, text)` ด้วย:
```python
        flex = build_job_flex(
            project_id=item["project_id"],
            title=_shorten_project_name(item.get("project_name") or ""),
            detail=text.split("\n", 1)[-1][:120] if "\n" in text else text[:120],
            doc_url=_lookup_pdf_url_from_rss(item["project_id"]),
        )
        success, error_type, error_msg = send_line_flex(token, item["line_user_id"], text[:200], flex)
```
> หมายเหตุ: ใช้ field จริงจาก `item` (ดู Step 2 ว่า dict มี key อะไร — `project_id`, `line_user_id`, `project_name`). ปรับ `title`/`detail` ให้ตรงกับข้อมูลที่มี

- [ ] **Step 4: ทดสอบ syntax + ส่ง flex จริงไป test account (VPS)**

```bash
python -c "import ast; ast.parse(open('scripts/Sebastian_LINE_Sender.py',encoding='utf-8').read()); print('syntax OK')"
```
Deploy (rm root + scp) → ssh VPS รัน python ส่ง flex ทดสอบไป line_user_id ของกัญจน์ (cust 2) → เห็น flex + 3 ปุ่มใน LINE

- [ ] **Step 5: Commit**

```bash
git add scripts/Sebastian_LINE_Sender.py
git commit -m "feat(line): ส่งงานเป็น flex message + ปุ่ม feedback (แทน text)"
```

---

## Task 4: Postback handler ใน webhook (เก็บ feedback project ตรง)

**Files:**
- Modify: `scripts/bms_api.py` (เพิ่ม postback branch ใน event loop + `_record_feedback_by_project`)

- [ ] **Step 1: เพิ่ม `_record_feedback_by_project` (project_id ตรงจาก postback)**

หลัง `_record_feedback` (ที่มีอยู่) เพิ่ม:
```python
def _record_feedback_by_project(user_id: str, action: str, project_id: str):
    """บันทึก feedback กับ project_id ที่ระบุตรง (จาก postback). upsert: 1 row/customer/project.
    คืน (project_name, project_id) | None"""
    with get_conn() as conn:
        cust = conn.execute("SELECT id FROM customers WHERE line_user_id=?", (user_id,)).fetchone()
        if not cust:
            return None
        cid = cust["id"]
        # upsert: ลบ feedback เดิมของ project นี้ก่อน (กดใหม่ทับเก่า)
        conn.execute("DELETE FROM feedback WHERE customer_id=? AND project_id=?", (cid, project_id))
        conn.execute(
            "INSERT INTO feedback (customer_id, project_id, action, raw_text, created_at) "
            "VALUES (?,?,?,?,?)", (cid, project_id, action, "", _now())
        )
        name_row = conn.execute(
            "SELECT project_name FROM projects_seen WHERE project_id=?", (project_id,)
        ).fetchone()
        pname = (name_row["project_name"] if name_row else "") or project_id
    return pname, project_id
```

- [ ] **Step 2: เพิ่ม postback branch ใน event loop**

ใน `line_webhook` event loop — หลัง branch `elif event.get("type") == "message":` (จบ block นั้น) เพิ่ม:
```python
        elif event.get("type") == "postback":
            reply_token = event.get("replyToken")
            data = ((event.get("postback") or {}).get("data") or "")
            parsed = None
            if data.startswith("fb:"):
                parts = data.split(":", 2)
                if len(parts) == 3 and parts[1] in ("interested", "relevant_low", "irrelevant") and parts[2]:
                    parsed = (parts[1], parts[2])
            if not parsed:
                continue
            action, project_id = parsed
            res = _record_feedback_by_project(user_id, action, project_id)
            if reply_token:
                label = {"interested": "👍 สนใจ", "relevant_low": "🤔 รับทราบ",
                         "irrelevant": "👎 ไม่เกี่ยว"}.get(action, "")
                await reply_message(reply_token, f"บันทึกแล้วครับ {label} ขอบคุณครับ 🎩")
```

- [ ] **Step 3: ทดสอบ postback parse logic (inline)**

สร้าง `scripts/_test_pb.py`:
```python
# จำลอง parse logic ใน handler
def parse(data):
    if data.startswith("fb:"):
        p = data.split(":", 2)
        if len(p) == 3 and p[1] in ("interested","relevant_low","irrelevant") and p[2]:
            return (p[1], p[2])
    return None
assert parse("fb:interested:69059297571") == ("interested", "69059297571")
assert parse("fb:bad:1") is None
assert parse("hello") is None
print("PASS task4")
```
Run: `python scripts/_test_pb.py` → Expected: `PASS task4` → แล้ว `rm scripts/_test_pb.py`

- [ ] **Step 4: syntax check**

Run: `python -c "import ast; ast.parse(open('scripts/bms_api.py',encoding='utf-8').read()); print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py
git commit -m "feat(api): postback handler — เก็บ feedback project ตรง + reply ขอบคุณ"
```

---

## Task 5: รายงาน feedback ใน Daily Digest

**Files:**
- Modify: `scripts/Sebastian_Daily_Digest.py` (เพิ่ม `feedback_summary_section` + เรียกใน main)

- [ ] **Step 1: เพิ่ม `feedback_summary_section`**

หาฟังก์ชัน section อื่น (เช่น `weekly_metrics_section`) เป็นแบบ แล้วเพิ่ม:
```python
def feedback_summary_section(conn) -> str:
    """สรุป feedback 7 วัน: 👍 value / 🤔 / 👎 matching ผิด (+ project list ให้กัญจน์ดู)"""
    rows = conn.execute(
        "SELECT action, COUNT(*) FROM feedback WHERE created_at >= date('now','-7 day') "
        "GROUP BY action"
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    interested = counts.get("interested", 0)
    low = counts.get("relevant_low", 0)
    irr = counts.get("irrelevant", 0)
    if interested + low + irr == 0:
        return "📊 Feedback (7วัน): ยังไม่มี feedback"
    lines = [f"📊 Feedback (7วัน): 👍 {interested} · 🤔 {low} · 👎 {irr}"]
    if interested:
        lines.append(f"  ✨ North-Star: มี {interested} งานที่ user สนใจ/น่าติดตาม")
    if irr:
        bad = conn.execute(
            "SELECT DISTINCT project_id FROM feedback WHERE action='irrelevant' "
            "AND created_at >= date('now','-7 day') LIMIT 10"
        ).fetchall()
        plist = ", ".join(b[0] for b in bad)
        lines.append(f"  ⚠️ matching ต้องดู (👎): {plist}")
    return "\n".join(lines)
```
> หมายเหตุ: ปรับ `conn` ให้ตรงกับวิธีที่ digest เชื่อม DB (ดูฟังก์ชัน section อื่นว่าใช้ conn จากไหน — `get_connection()` จาก Sebastian_Customer_DB)

- [ ] **Step 2: เรียกใน main()**

หาจุดที่ digest ประกอบ message (เรียก section อื่นๆ) → เพิ่ม `feedback_summary_section(conn)` เข้าไปใน body ที่ส่ง Discord/รายงาน

- [ ] **Step 3: ทดสอบ section (inline บน VPS — มี feedback data)**

หลัง deploy + มี feedback จริง (จาก Task 3-4 test) → ssh VPS รัน:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 'cd /opt/bms/app && /opt/bms/venv/bin/python -c "
import sys; sys.path.insert(0,\"scripts\")
from Sebastian_Customer_DB import get_connection
from Sebastian_Daily_Digest import feedback_summary_section
with get_connection() as c: print(feedback_summary_section(c))
"'
```
Expected: เห็นสรุป feedback (counts)

- [ ] **Step 4: syntax + commit**

```bash
python -c "import ast; ast.parse(open('scripts/Sebastian_Daily_Digest.py',encoding='utf-8').read()); print('OK')"
git add scripts/Sebastian_Daily_Digest.py
git commit -m "feat(digest): สรุป feedback (👍 value / 👎 matching ผิด) ให้กัญจน์"
```

---

## Task 6: Deploy + Integration verify (end-to-end)

**Files:** (deploy ทั้ง 3 ไฟล์ที่แก้)

- [ ] **Step 1: Deploy ไป VPS (LINE_Sender + bms_api + Daily_Digest)**

```bash
for f in Sebastian_LINE_Sender.py bms_api.py Sebastian_Daily_Digest.py; do
  ssh -i ~/.ssh/bms_vps bms@45.76.156.166 "cd /opt/bms/app/scripts && rm -f $f"
  scp -i ~/.ssh/bms_vps scripts/$f bms@45.76.156.166:/opt/bms/app/scripts/$f
done
```

- [ ] **Step 2: Restart bms_api (โหลด webhook ใหม่)**

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 'systemctl restart bms-api.service && sleep 2 && systemctl is-active bms-api.service'
```
Expected: `active`

- [ ] **Step 3: ส่ง flex งานทดสอบไป LINE กัญจน์ (cust 2)**

ssh VPS รัน LINE_Sender ส่ง flex 1 งานจริงไป line_user_id ของกัญจน์ → กัญจน์เห็น flex + 3 ปุ่มใน LINE

- [ ] **Step 4: กัญจน์กดปุ่ม → verify feedback เขียน**

กัญจน์กด 👍 ในมือถือ → ssh VPS เช็ค:
```bash
ssh -i ~/.ssh/bms_vps bms@45.76.156.166 'python3 -c "
import sqlite3; c=sqlite3.connect(\"/opt/bms/data/bms_customers.db\")
for r in c.execute(\"SELECT customer_id,project_id,action,created_at FROM feedback ORDER BY created_at DESC LIMIT 3\"): print(r)
"'
```
Expected: เห็น feedback row (action=interested, project_id ตรง) + กัญจน์เห็น reply "บันทึกแล้วครับ 👍"

- [ ] **Step 5: กดซ้ำ (เปลี่ยนใจ) → verify upsert (1 row/project)**

กัญจน์กด 👎 งานเดิม → เช็ค feedback: ต้องมี **1 row** ของ project นั้น (action=irrelevant ทับ interested)

- [ ] **Step 6: Final commit + push**

```bash
git add -A
git commit -m "feat: LINE feedback buttons — end-to-end (ปุ่ม→webhook→เก็บ→reply→digest)"
git push origin main
```

---

## Notes
- **ไม่แตะ existing text feedback** (`_match_feedback`/`_record_feedback`) — เก็บไว้เป็น fallback
- **feedback table** มี schema พร้อม — ไม่ migrate
- **Defer (ไม่ทำใน plan นี้):** portal ติดดาว · auto-tune matching · budget filter จาก 🤔
- **Rollback:** ถ้า flex มีปัญหา → revert LINE_Sender กลับ send_line_push (text) ได้ทันที
