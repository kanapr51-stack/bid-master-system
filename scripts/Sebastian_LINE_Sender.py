"""
Sebastian_LINE_Sender.py — LINE push notification worker v1

Runs every 1 min via Task Scheduler (BidMaster_LINE_Sender).
Single iteration per run: recover stuck → acquire 1 item → send → mark result.

Flags:
  --dry-run   render message + log queue transitions, skip actual LINE API call
              (ใช้ก่อน live send เพื่อ validate formatting + delivery semantics)

Error classification:
  retryable : 429, 5xx, timeout, network error (max 3 retries, 5-min fixed delay)
  terminal  : 400/403 invalid user, blocked, unlinked LINE account

State transitions handled by SubscriptionStore.
Logs: logs/line_sender/sender_YYYYMMDD.log
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests as req_lib

sys.path.insert(0, str(Path(__file__).parent))
import bms_paths  # noqa: E402  — single runtime-state authority (BMS_DATA_DIR)
from Sebastian_Customer_DB import (
    SubscriptionStore, init_schema, worker_id, _now,
)
import follow_token  # noqa: E402

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Constants ─────────────────────────────────────────────────────────────────

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
BATCH_SIZE    = 1   # correctness > throughput during pilot
LOG_DIR       = Path(__file__).parent.parent / "logs" / "line_sender"
TZ_TH         = timezone(timedelta(hours=7))
PUBLIC_BASE_URL = os.getenv("BMS_PUBLIC_BASE_URL", "https://api.butler-bms.com")

TYPE_LABELS = {
    "D0": "ประกาศจัดซื้อจัดจ้าง",
    "W0": "ประกาศผลผู้ชนะ",
}

# ── Feedback postback (P2 — ปุ่มกดใน LINE) ──────────────────────────────────
# action labels (ตรงกับ feedback table + bms_api postback handler)
FB_ACTIONS = {
    "star":       "⭐ ติดตามงานนี้",
    "irrelevant": "❌ ไม่เกี่ยว",
}


def build_postback_data(action: str, project_id: str) -> str:
    """postback data: star → 'star:<pid>' (handler ใหม่ — ติดตามงาน) ·
    อื่นๆ → 'fb:<action>:<pid>' (handler feedback เดิม)"""
    return f"star:{project_id}" if action == "star" else f"fb:{action}:{project_id}"


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


def build_job_flex(project_id: str, title: str, detail: str, doc_url: str = "",
                   with_feedback: bool = True) -> dict:
    """สร้าง flex bubble: งาน (body) + ปุ่ม feedback postback (footer — เฉพาะ feedback authority).
    with_feedback=False → ไม่มีปุ่ม (ครอบครัวได้แจ้งงานแต่ไม่กด feedback — กัน noise/สับสน).
    คืน contents dict (ใส่ใน message type=flex)"""
    body_contents = [
        {"type": "text", "text": "🏗️ " + title[:300], "wrap": True, "weight": "bold", "size": "sm"},
        {"type": "text", "text": detail[:1000], "wrap": True, "size": "sm", "color": "#444444", "margin": "md"},
    ]
    if doc_url:
        body_contents.append({
            "type": "button", "style": "link", "height": "sm", "margin": "md",
            "action": {"type": "uri", "label": "📋 ดูรายละเอียดงาน", "uri": doc_url},
        })
    bubble = {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "contents": body_contents},
    }
    if with_feedback:
        footer_btns = [{
            "type": "button", "style": "secondary", "height": "sm",
            "action": {"type": "postback", "label": label,
                       "data": build_postback_data(action, project_id),
                       "displayText": label},
        } for action, label in FB_ACTIONS.items()]
        bubble["footer"] = {"type": "box", "layout": "vertical", "spacing": "sm", "contents": footer_btns}
    return bubble


def _feedback_authority_ids() -> set:
    """customer_id ที่มีสิทธิ์ feedback (beta: เฉพาะกัญจน์ — กัน noise จาก user ที่กดลองเล่น).
    config/feedback_authority.json → {"customer_ids":[..]}. ไม่มีไฟล์/ว่าง = ทุกคน (backward-compat)."""
    try:
        p = Path(__file__).parent.parent / "config" / "feedback_authority.json"
        if p.exists():
            ids = json.loads(p.read_text(encoding="utf-8")).get("customer_ids")
            if ids:
                return set(ids)
    except Exception:
        pass
    return set()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_line_token() -> str:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEBASTIAN_LINE_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    token = os.environ.get("SEBASTIAN_LINE_TOKEN", "")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN not found in .env or environment")
    return token


def _lookup_pdf_url_from_rss(project_id: str) -> str:
    """Find PDF link from rss_queue.json by project_id (best-effort, non-fatal)."""
    try:
        import json as _json
        rss_path = bms_paths.runtime_path("rss_queue.json")
        if not rss_path.exists():
            return ""
        items = _json.loads(rss_path.read_text(encoding="utf-8-sig"))
        for item in items:
            if item.get("projectId") == project_id:
                return item.get("link") or ""
    except Exception:
        pass
    return ""


def _clean_project_name(name: str) -> str:
    """ลบ prefix/suffix ที่ไม่มีความหมายออก — คืน 'ชื่อเต็ม' (ไม่ตัดความยาว)"""
    prefixes = [
        "ประกวดราคาจ้างก่อสร้าง", "ประกวดราคาจ้าง", "ประกวดราคาซื้อ",
        "ซื้อ", "จ้าง", "จ้างก่อสร้าง", "ประกวดราคา",
    ]
    result = name.strip()
    for p in prefixes:
        if result.startswith(p):
            result = result[len(p):].lstrip()
            break
    # ตัด suffix เช่น "ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)"
    for suffix in [" ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
                   " โดยวิธีเฉพาะเจาะจง", " ด้วยวิธีคัดเลือก"]:
        if result.endswith(suffix):
            result = result[:-len(suffix)].rstrip()
    return result or name


def _shorten_project_name(name: str, max_len: int = 60) -> str:
    """เวอร์ชันย่อ (ใช้ที่ digest/log) — clean แล้วตัดความยาว"""
    result = _clean_project_name(name)
    if len(result) > max_len:
        result = result[:max_len] + "..."
    return result or name[:max_len]


def _fmt_budget(budget: float) -> str:
    """แสดงราคากลางในรูปแบบอ่านง่าย เช่น 21.7 ล้าน / 850,000"""
    if not budget:
        return "ไม่ระบุ"
    if budget >= 1_000_000:
        return f"{budget / 1_000_000:.1f} ล้านบาท"
    return f"{int(budget):,} บาท"


def _fmt_thai_date(iso_date: str) -> str:
    """'2026-06-08' → '8 มิ.ย.' """
    if not iso_date:
        return ""
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(iso_date, "%Y-%m-%d")
        months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                  "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
        return f"{d.day} {months[d.month]}"
    except Exception:
        return iso_date


def _days_remaining(bid_date_iso: str) -> int | None:
    """Days from today to bid_submit_date. Negative = past."""
    if not bid_date_iso:
        return None
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        TZ_TH = _tz(_td(hours=7))
        d = _dt.strptime(bid_date_iso, "%Y-%m-%d").replace(tzinfo=TZ_TH)
        today = _dt.now(TZ_TH).replace(hour=0, minute=0, second=0, microsecond=0)
        return (d - today).days
    except Exception:
        return None


def format_notification(project_id: str, province: str = "",
                         announce_type: str = "D0", budget: float = 0,
                         project_name: str = "", dept_name: str = "",
                         deliver_day: int = 0, report_date: str = "",
                         bid_submit_date: str = "", bid_submit_time: str = "",
                         is_backfill: bool = False,
                         source_stage: str = "api_enriched") -> str:
    """
    v2 Mobile-first format — optimize สำหรับ 3-second decision scan
    ลำดับ: geography → project → money → agency → DEADLINE → timeline → announced
    """
    # ชื่องาน (เต็ม) แสดงเป็น header ของการ์ด flex แล้ว — body ไม่ต้องซ้ำ
    lines = []

    # competitive intel: resolve ทุกงาน D0 (เปิดยื่นซอง) เพื่อใช้ ต./อ. ในบรรทัด 📍 + บล็อก intel
    # — ไม่ผูกกับการติดตาม (กดติดตามตอน D0 ก็เห็น intel; อุด follow-timing gap)
    intel_ctx = None
    if announce_type == "D0":
        try:
            import cgd_intel
            intel_ctx = cgd_intel.intel_context(province, project_name, dept_name, project_id, budget)
        except Exception:
            intel_ctx = None   # intel = value-add — ห้ามทำ D0 notification พัง

    if source_stage == "followed_bid_open":
        lines.append("⭐ งานที่คุณติดตามกำหนดวันยื่นซองแล้ว!")
    elif announce_type == "D0":
        lines.append("🔔 พบงานเปิดกำหนดวันยื่นซองใหม่")
    elif source_stage.startswith("province_tor_review"):
        lines.append("📋 รับฟังคำวิจารณ์ (ร่าง TOR — ยังไม่เปิดประมูล)")
    elif is_backfill:
        lines.append("📦 โครงการที่ยังเปิดประมูลอยู่")
    else:
        lines.append("🔔 พบโครงการใหม่")

    # 📍 ระบุ ต./อ. ถ้า resolve ได้ (ละเอียดกว่าจังหวัดเฉยๆ)
    if intel_ctx and intel_ctx.get("amphoe"):
        _tb = f"ต.{intel_ctx['tambon']} " if intel_ctx.get("tambon") else ""
        lines.append(f"📍 {_tb}อ.{intel_ctx['amphoe']} จ.{province}")
    else:
        lines.append(f"📍 {province or 'ไม่ระบุจังหวัด'}")
    lines.append(f"💰 ราคากลาง {_fmt_budget(budget)}")

    if dept_name:
        lines.append(f"🏢 {dept_name}")

    # ⏰ deadline — high priority placement after agency
    if bid_submit_date:
        thai_date = _fmt_thai_date(bid_submit_date)
        time_part = f" {bid_submit_time}" if bid_submit_time else ""
        lines.append(f"⏰ ยื่นซอง {thai_date}{time_part}")
        days = _days_remaining(bid_submit_date)
        if days is not None and days >= 0:
            lines.append(f"⌛ เหลือ {days} วัน")

    if deliver_day:
        lines.append(f"⏱ ระยะเวลา {deliver_day} วัน")

    if report_date:
        lines.append(f"📅 ประกาศ {report_date}")

    # competitive intel block (resolve ไว้ข้างบนแล้ว — เฉพาะการ์ดเปิดประมูล D0)
    if intel_ctx:
        lines.append("━━━━━━━━━━━━━")
        lines.extend(intel_ctx["lines"])
        if intel_ctx.get("prediction") and project_id:   # เก็บคำทำนายไว้เทียบตอนประกาศผล (closed-loop)
            try:
                from Sebastian_Customer_DB import save_prediction
                save_prediction({"project_id": project_id, **intel_ctx["prediction"]})
            except Exception:
                pass

    lines.append(f"\n🔑 {project_id}")

    if source_stage == "rss_provisional":
        lines.append("📡 ข้อมูลเบื้องต้นจาก RSS")
    elif source_stage in ("province_soft_location", "province_tor_review_soft"):
        lines.append("⚠️ พื้นที่ไม่ชัด — โปรดตรวจสอบว่าอยู่ในเขตที่รับงาน")

    return "\n".join(lines)


def _text_message(text: str, quick_reply=None) -> dict:
    """LINE text message dict + แนบ quickReply (ปุ่มลอย) ถ้ามี items."""
    msg = {"type": "text", "text": text}
    if quick_reply:
        msg["quickReply"] = {"items": quick_reply}
    return msg


def _quick_reply_items(project_id: str, following: bool) -> list:
    """ปุ่มลอยใต้ข้อความ D0: ⭐ ติดตาม (ถ้ายังไม่ตาม) + ❌ ไม่เกี่ยว. postback เดียวกับการ์ด flex."""
    items = []
    if not following:
        items.append({"type": "action", "action": {
            "type": "postback", "label": FB_ACTIONS["star"],
            "data": build_postback_data("star", project_id), "displayText": FB_ACTIONS["star"]}})
    items.append({"type": "action", "action": {
        "type": "postback", "label": FB_ACTIONS["irrelevant"],
        "data": build_postback_data("irrelevant", project_id), "displayText": FB_ACTIONS["irrelevant"]}})
    return items


def build_follow_link(line_user_id: str, project_id: str) -> str:
    """ลิงก์ติดตามงาน (signed token, ต่อคน-ต่องาน). คืน '' ถ้า make_token พลาด (ห้ามทำ D0 พัง)."""
    try:
        return PUBLIC_BASE_URL.rstrip("/") + "/follow?t=" + \
            follow_token.make_token(line_user_id, project_id)
    except Exception as e:
        print(f"[build_follow_link] follow_token error (ส่งต่อไม่มีลิงก์): {e}", file=sys.stderr)
        return ""


def send_line_push(token: str, line_user_id: str, text: str, quick_reply=None) -> tuple[bool, str, str]:
    """
    Returns (success, error_type, error_msg).
    error_type: '' | 'retryable' | 'terminal'
    quick_reply: list ของ quick-reply action items (None = ข้อความเปล่า เหมือนเดิม).
    """
    try:
        r = req_lib.post(
            LINE_PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": line_user_id, "messages": [_text_message(text, quick_reply)]},
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
        # 400/403 — invalid user ID, blocked, unlinked
        return False, "terminal", f"HTTP {r.status_code}: {detail}"
    except req_lib.Timeout:
        return False, "retryable", "timeout"
    except Exception as e:
        return False, "retryable", str(e)[:200]


def _fmt_baht(v) -> str:
    """ราคา (str/num) → '1,234,567' (ตัดทศนิยม). คืน str เดิมถ้า parse ไม่ได้."""
    try:
        return f"{int(round(float(v))):,}"
    except (ValueError, TypeError):
        return str(v or "")


def _accuracy_line(cmp: dict, actual_price) -> str:
    """บรรทัด 🎯 เทียบ 'ราคาที่คาด (ค่ากลาง/ปกติ)' กับราคาที่ชนะจริง — framing win/lose สำหรับคนประมูล:
    คาด ≤ ราคาชนะ → ยื่นราคานี้ก็ชนะ → 'ความแม่นยำ X%'.
    คาด > ราคาชนะ → ยื่นแล้วแพ้ (ผู้ชนะลงลึกกว่าคาด) → 'ความคลาดเคลื่อนจากราคาชนะ X%'.
    fallback: prediction เก่าไม่มี median → เทียบกรอบบน (เดิม). คืน '' ถ้า actual แปลงไม่ได้."""
    try:
        actual = float(actual_price)
    except (TypeError, ValueError):
        return ""
    med = cmp.get("pred_med")
    if med and actual > 0:
        med = float(med)
        if med <= actual:                       # ยื่นราคาที่คาด → ชนะ
            acc = max(0.0, 100 - abs(med - actual) / actual * 100)
            return (f"🎯 ความแม่นยำ {acc:.1f}% (คาด {_fmt_baht(med)} · ชนะจริง "
                    f"{_fmt_baht(actual)}) ✅ ราคาที่คาดชนะได้")
        dev = (med - actual) / actual * 100      # คาดสูงกว่าราคาชนะ → แพ้
        return (f"📉 ความคลาดเคลื่อนจากราคาชนะ {dev:.1f}% (คาด {_fmt_baht(med)} · ชนะจริง "
                f"{_fmt_baht(actual)}) ⚠️ ราคาที่คาดจะแพ้")
    if cmp.get("upper") and cmp.get("error_pct") is not None:   # fallback เทียบกรอบบน
        acc = max(0.0, 100 - abs(cmp["error_pct"]))
        inr = " ✅อยู่ในกรอบ" if cmp.get("held") else ""
        return (f"🎯 ความแม่นยำ {acc:.1f}% (คาดกรอบบน {_fmt_baht(cmp['upper'])} · จริง "
                f"{_fmt_baht(actual)}){inr}")
    return ""


def format_prelim_notification(project_name: str, budget, prelim: dict, cmp: dict, project_id: str = "") -> str:
    """Round 1 — สรุปราคาเบื้องต้น (ยังไม่ทางการ). cmp = compare_prediction_provisional หรือ None."""
    lines = ["🔔 ผลเสนอราคาเบื้องต้น (ยังไม่ทางการ)"]
    if project_name:
        lines.append(f"🏗 {project_name[:80]}")
    lines.append(f"💰 ราคากลาง {_fmt_baht(budget)} บาท")
    n = prelim.get("num_bidders")
    if prelim.get("has_price") and prelim.get("lowest_price"):
        low = prelim["lowest_price"]
        lines.append(f"📊 ราคาต่ำสุดที่เสนอ: {_fmt_baht(low)} บาท · ผู้เสนอ {n} ราย")
        if cmp:
            acc_line = _accuracy_line(cmp, low)
            if acc_line:
                lines.append(acc_line)
            try:
                d = (1 - float(low) / float(budget)) * 100
                lines.append(f"   (ส่วนลดจริง {d:.0f}%)")
            except (ValueError, TypeError, ZeroDivisionError):
                pass
    else:
        lines.append(f"📊 มีผู้เสนอ {n} ราย · ราคายังไม่เปิดเผย (เกณฑ์ 2 ซอง) · รอผลทางการ")
    lines.append("⏳ รอประกาศผู้ชนะทางการ — จะแจ้งรายชื่อ + คู่แข่งอีกครั้ง")
    if project_id:
        lines.append(f"🔑 {project_id}")
    return "\n".join(lines)


def format_winner(project_name: str, winner: str, price_agree: str,
                  competitors: list = None, budget=0, project_id: str = "") -> str:
    """การ์ดแจ้งผู้ชนะของงานที่ติดตาม (⭐) — ผู้ชนะ + ราคา + คู่แข่งทุกราย + ราคา (competitive intel).
    competitors: list[{'name','price'}] (ไม่รวมผู้ชนะ, dedupe แล้วโดย caller)."""
    competitors = competitors or []
    lines = ["⭐ งานที่คุณติดตาม — ประกาศผู้ชนะแล้ว"]
    if project_name:
        lines.append(f"🏗️ {project_name[:80]}")
    lines.append(f"🏆 ผู้ชนะ: {winner}")
    lines.append(f"💵 ราคาที่ชนะ {_fmt_baht(price_agree)} บาท")
    try:
        if budget and float(budget) > 0 and float(price_agree) > 0:
            disc = (1 - float(price_agree) / float(budget)) * 100
            lines.append(f"📉 ต่ำกว่าราคากลาง {disc:.1f}%")
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    if competitors:
        lines.append(f"\n👥 คู่แข่งที่ยื่น ({len(competitors)} ราย):")
        for c in competitors:
            lines.append(f"  • {(c.get('name') or '?')[:32]} — {_fmt_baht(c.get('price'))}")
    else:
        lines.append("\n👤 ผู้ยื่นรายเดียว (ไม่มีคู่แข่ง)")
    if project_id:
        lines.append(f"\n🔑 {project_id}")
    return "\n".join(lines)


_TAG_LABEL = {"warned": "✅เราเตือน", "regular_missed": "🔸เจ้าประจำที่หลุด top3", "newcomer": "หน้าใหม่"}


def format_winner_detailed(project_name, winner, price_agree, budget, analyzed, cmp, acc, market_disc, project_id=""):
    """Round 2 — ผู้ชนะ + ความแม่น(กรอบบน)+สะสม + breakdown ต่อราย(ประวัติ/ป้าย) + ส่วนลด vs ตลาด.
    analyzed = cgd_intel.analyze_bidders(...). cmp = compare_prediction(...). acc = prediction_accuracy_summary()."""
    lines = ["⭐ งานที่ติดตาม — ประกาศผู้ชนะแล้ว"]
    if project_name:
        lines.append(f"🏗 {project_name[:80]}")
    win_disc = ""
    try:
        win_disc = f" (ลด {(1 - float(price_agree)/float(budget))*100:.1f}%)"
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    lines.append(f"🏆 ผู้ชนะ: {winner} · {_fmt_baht(price_agree)}{win_disc}")
    if cmp:
        line = _accuracy_line(cmp, price_agree)
        if line:
            if acc and acc.get("verified"):
                line += f" · สะสมอยู่ในกรอบ {acc['in_range']}/{acc['verified']}"
            lines.append(line)
    if analyzed:
        lines.append(f"📊 ผู้ยื่น {len(analyzed)} ราย (เรียงราคา · เทียบประวัติพื้นที่):")
        for i, b in enumerate(analyzed, 1):
            crown = "🏆" if b["is_winner"] else "  "
            h = b["hist"]
            if h["n"] > 0:
                _lv = h.get("ewma") if h.get("ewma") is not None else h["median"]
                hist_s = f"{h['scope']}ล่าสุด~{_lv:.0f}%({h['n']}ครั้ง){b['trend'] or ''}"
            else:
                hist_s = "ไม่มีประวัติ"
            d = f"ลด{b['discount']:.0f}%" if b["discount"] is not None else ""
            lines.append(f" {i}){crown} {b['name'][:24]} {_fmt_baht(b['price'])} {d} · {hist_s} · {_TAG_LABEL.get(b['tag'],'')}")
    if market_disc is not None and analyzed:
        wd = next((b["discount"] for b in analyzed if b["is_winner"]), None)
        if wd is not None:
            rel = "มากกว่า" if wd > market_disc + 1 else "น้อยกว่า" if wd < market_disc - 1 else "พอๆกัน"
            lines.append(f"📉 ผู้ชนะลด {wd:.0f}% vs ตลาดตำบล {market_disc:.0f}% ({rel})")
    if project_id:
        lines.append(f"🔑 {project_id}")
    return "\n".join(lines)


def _winner_card_from_results(item: dict, results: list) -> tuple:
    """สร้าง (alt_text, flex) การ์ดผู้ชนะ จาก bid_results — เลือกผู้ชนะ + dedupe คู่แข่งตามชื่อบริษัท
    (getProcureResult คืน per-line-item อาจซ้ำ). ไม่มีปุ่ม (lifecycle จบที่ W0)."""
    win = next((b for b in results if b.get("is_winner")), None)
    seen, comps = set(), []
    for b in results:
        if b.get("is_winner"):
            continue
        nm = b.get("bidder_name")
        if nm and nm not in seen:
            seen.add(nm)
            comps.append({"name": nm, "price": b.get("price_proposal")})
    pname = item.get("project_name") or item.get("project_id", "")
    text = format_winner(
        pname, win["bidder_name"] if win else "—",
        win["price_agree"] if win else "", comps,
        budget=float(item.get("budget") or 0), project_id=item.get("project_id", ""))
    # closed-loop: บรรทัดเทียบราคาคาด vs จริง (เมื่อ prediction verified แล้ว) — credibility
    try:
        from Sebastian_Customer_DB import get_prediction
        p = get_prediction(item.get("project_id", ""))
        if p and p.get("verified_at") and p.get("area_price_lo") is not None:
            verdict = "✅ ตรง" if p.get("in_range") else "❌ ไม่ตรง"
            text += (f"\n🎯 Sebastian คาด {p['area_price_lo']/1e6:.1f}–{p['area_price_hi']/1e6:.1f} ลบ. "
                     f"→ {verdict} (คลาด {p.get('error_pct') or 0:.0f}%)")
    except Exception:
        pass
    flex = build_job_flex(item.get("project_id", ""), "🏆 ประกาศผู้ชนะ", text, with_feedback=False)
    return ("ประกาศผู้ชนะ | " + text)[:400], flex


def _deadline_from_db(project_id: str) -> tuple[str, str]:
    """fallback อ่าน deadline ที่ resolve+เก็บไว้ใน project_locations (สำหรับงาน province_api
    ที่ไม่มี pdf_url ให้ enrich — เช่น ⭐ bid-open followup). คืน (date 'YYYY-MM-DD', time 'HH:MM')."""
    try:
        from Sebastian_Customer_DB import get_connection
        with get_connection() as conn:
            try:
                r = conn.execute("SELECT deadline, deadline_time FROM project_locations "
                                 "WHERE project_id=?", (project_id,)).fetchone()
            except Exception:   # คอลัมน์ deadline_time ยังไม่ migrate → ดึงแค่ deadline (date)
                r = conn.execute("SELECT deadline FROM project_locations WHERE project_id=?",
                                 (project_id,)).fetchone()
        dl = (r[0] if r else "") or ""
        if not dl:
            return "", ""
        date = dl[:10]
        # ช่วงเวลายื่นเก็บแยกคอลัมน์ (province_api path) — fallback time ใน string เดิม (legacy)
        tm = (r[1] if r and len(r) > 1 else "") or (dl[11:16] if len(dl) >= 16 else "")
        return date, tm
    except Exception:
        return "", ""


def _round2_warned_names(conn, province, tokens, loc) -> list:
    """ชื่อ top-3 คู่แข่งที่เตือนตอน D0 (= top3 ของ scope block ตำบล/อำเภอ/จังหวัด)."""
    import cgd_intel as _ci
    try:
        rows, _scope, _lv = _ci.select_competitors(province, tokens, loc.get("tambon", ""), loc.get("amphoe"), conn)
        from collections import Counter
        return [w for w, _ in Counter(r["winner"] for r in rows if r.get("winner")).most_common(_ci.SHOW_N)]
    except Exception:
        return []


def _round2_market_disc(ctx):
    """ส่วนลดตลาด (median ของ scope) จาก prediction. None ถ้าไม่มี."""
    if not ctx or not ctx.get("prediction"):
        return None
    p = ctx["prediction"]
    lo, hi = p.get("area_disc_lo"), p.get("area_disc_hi")
    return round((lo + hi) / 2, 1) if lo is not None and hi is not None else None


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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LINE notification sender worker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render message + log transitions, skip actual LINE API call")
    args, _ = parser.parse_known_args()
    dry_run = args.dry_run

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"sender_{datetime.now().strftime('%Y%m%d')}.log"

    def log(msg: str):
        line = f"[{_now()}] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    init_schema()
    store = SubscriptionStore()
    wid   = worker_id()
    mode  = "DRY RUN" if dry_run else "LIVE"
    log(f"=== LINE Sender start worker_id={wid} mode={mode} ===")

    # Step 1: recover stuck 'sending' items (crash window cleanup)
    recovered = store.recover_stuck_sending()
    if recovered:
        log(f"Recovered {recovered} stuck sending → pending (worker_timeout)")

    # Step 2: load LINE token (skip validation in dry-run)
    token = ""
    if not dry_run:
        try:
            token = _load_line_token()
        except RuntimeError as e:
            log(f"ABORT: {e}")
            return

    # Step 3: atomic acquire
    items = store.acquire_batch(batch_size=BATCH_SIZE, wid=wid)
    if not items:
        log("No pending items — exit")
        return

    item = items[0]
    log(
        f"Acquired queue_id={item['id']} project={item['project_id']} "
        f"customer={item['customer_id']} retry={item['retry_count']}"
    )

    # 📊 prelim notification (followed_prelim): Round 1 — ราคาเบื้องต้น (ยังไม่ทางการ)
    # (source_stage-gated → inert กับ notification อื่นทั้งหมด)
    if item.get("source_stage") == "followed_prelim":
        import prelim_summary as _ps
        import cgd_intel as _ci
        pid = item["project_id"]
        budget = item.get("budget") or 0
        pr = _ps.fetch_prelim_summary(pid)
        cmp = _ci.compare_prediction_provisional(pid, pr.get("lowest_price")) if pr.get("has_price") else None
        pname = _clean_project_name(item.get("project_name") or "") or pid
        text = format_prelim_notification(pname, budget, pr, cmp, pid)
        if dry_run:
            log("─── DRY RUN: prelim notification ───")
            for ln in text.splitlines():
                log("  " + ln)
            store.mark_delivery_result(item["id"], item["customer_id"], item["project_id"],
                                       status="failed", error="dry_run", error_type="retryable")
            log("=== LINE Sender done (prelim dry-run) ===")
            return
        success, error_type, error_msg = send_line_push(token, item["line_user_id"], text, quick_reply=None)
        store.mark_delivery_result(item["id"], item["customer_id"], item["project_id"],
                                   status="sent" if success else "failed",
                                   error=error_msg, error_type=error_type)
        log(f"📊 prelim sent={success} {item['project_id']} cust{item['customer_id']} ({error_msg})")
        log("=== LINE Sender done (prelim) ===")
        return

    # ⭐ winner notification (followed_winner): Round 2 — ผู้ชนะ + ความแม่น + breakdown ต่อราย
    # (source_stage-gated → inert กับ notification อื่นทั้งหมด)
    if item.get("source_stage") == "followed_winner":
        import cgd_intel as _ci
        from Sebastian_Customer_DB import prediction_accuracy_summary, get_connection as _get_conn
        results = store.get_bid_results(item["project_id"])
        win = next((b for b in results if b.get("is_winner")), None)
        winner_name = (win or {}).get("bidder_name", "?")
        price_agree = (win or {}).get("price_agree") or (win or {}).get("price_proposal") or 0
        budget = item.get("budget") or 0
        pname = _clean_project_name(item.get("project_name") or "") or item["project_id"]
        with _get_conn() as _c:
            ctx = _ci.intel_context(item.get("province", ""), item.get("project_name", ""),
                                    item.get("dept_name", ""), item["project_id"], budget, _c)
            tokens = _ci.match_keywords(item.get("project_name", ""))
            loc = _ci.resolve_location(item["project_id"], item.get("project_name", ""),
                                       item.get("dept_name", ""), item.get("province", ""), _c)
            warned = _round2_warned_names(_c, item.get("province", ""), tokens, loc)
            analyzed = _ci.analyze_bidders(_c, item.get("province", ""), tokens,
                                           loc["tambon"], loc["amphoe"],
                                           budget, results, warned)
            market_disc = _round2_market_disc(ctx)
        cmp = _ci.compare_prediction(item["project_id"], float(price_agree) if price_agree else 0)
        acc = prediction_accuracy_summary()
        text = format_winner_detailed(pname, winner_name, price_agree, budget, analyzed, cmp, acc,
                                      market_disc, item["project_id"])
        if dry_run:
            log("─── DRY RUN: winner detailed ───")
            for ln in text.splitlines():
                log("  " + ln)
            store.mark_delivery_result(item["id"], item["customer_id"], item["project_id"],
                                       status="failed", error="dry_run", error_type="retryable")
            log("=== LINE Sender done (winner dry-run) ===")
            return
        success, error_type, error_msg = send_line_push(token, item["line_user_id"], text, quick_reply=None)
        store.mark_delivery_result(item["id"], item["customer_id"], item["project_id"],
                                   status="sent" if success else "failed",
                                   error=error_msg, error_type=error_type)
        log(f"⭐ winner sent={success} {item['project_id']} cust{item['customer_id']} ({error_msg})")
        log("=== LINE Sender done (winner) ===")
        return

    # Step 4a: API enrichment (opportunistic — skip if WAF state unknown/blocked)
    dept_name   = item.get("dept_name") or ""
    budget      = float(item.get("budget") or 0)
    deliver_day = 0
    report_date = ""

    def _api_state() -> str:
        """Read api_ingestion_state.json → api_state value, 'UNKNOWN' if unreadable."""
        try:
            import json as _json
            state_path = bms_paths.runtime_path("api_ingestion_state.json")
            if state_path.exists():
                return _json.loads(state_path.read_text(encoding="utf-8-sig")).get("api_state", "UNKNOWN")
        except Exception:
            pass
        return "UNKNOWN"

    if not dept_name or not budget:
        # Step 4a-i: cache lookup from projects_seen
        try:
            import sqlite3 as _sql
            from Sebastian_Customer_DB import DB_PATH as _DB
            _conn = _sql.connect(str(_DB))
            _row = _conn.execute(
                "SELECT dept_name, budget FROM projects_seen WHERE project_id=?",
                (item["project_id"],)
            ).fetchone()
            _conn.close()
            if _row and _row[0]:
                dept_name = _row[0]
                budget    = float(_row[1] or 0) or budget
                log(f"  API enrich: cache hit dept={dept_name[:30]} budget={budget}")
        except Exception:
            pass

    if not dept_name or not budget:
        # Step 4a-ii: live API call (only if cache miss)
        api_state = _api_state()
        if api_state == "HEALTHY":
            try:
                from process5_http_client import get_procurement_detail
                enriched = get_procurement_detail(item["project_id"])
                if enriched.get("valid"):
                    dept_name   = enriched.get("dept_sub_name") or dept_name
                    budget      = enriched.get("budget") or budget
                    deliver_day = enriched.get("deliver_day") or 0
                    report_date = enriched.get("report_date") or ""
                    log(f"  API enrich: live dept={dept_name[:30]} budget={budget} days={deliver_day}")
                    # write back to cache
                    try:
                        import sqlite3 as _sql
                        from Sebastian_Customer_DB import DB_PATH as _DB
                        _conn = _sql.connect(str(_DB))
                        _conn.execute(
                            "UPDATE projects_seen SET dept_name=?, budget=? WHERE project_id=?",
                            (dept_name, budget, item["project_id"])
                        )
                        _conn.commit()
                        _conn.close()
                    except Exception:
                        pass
            except Exception as e:
                log(f"  API enrich failed (non-fatal): {e}")
        else:
            log(f"  API enrich skipped (api_state={api_state}) — RSS-only delivery")

    # Step 4b: PDF enrichment for bid_submit_date (lazy + cached)
    bid_submit_date = ""
    bid_submit_time = ""
    pdf_url = item.get("pdf_url") or _lookup_pdf_url_from_rss(item["project_id"])
    if pdf_url:
        try:
            from process5_http_client import get_pdf_enrichment
            from Sebastian_Customer_DB import DB_PATH
            penrich = get_pdf_enrichment(item["project_id"], pdf_url, str(DB_PATH))
            bid_submit_date = penrich.get("bid_submit_date") or ""
            bid_submit_time = penrich.get("bid_submit_time") or ""
            cache_label = "cached" if penrich.get("cache_hit") else "fresh"
            log(f"  PDF enrich ({cache_label}): status={penrich.get('enrichment_status')} "
                f"bid={bid_submit_date} time={bid_submit_time} "
                f"dl={penrich.get('pdf_download_ms')}ms parse={penrich.get('pdf_parse_ms')}ms")
        except Exception as e:
            log(f"  PDF enrich failed (non-fatal): {e}")

    # Step 4c: fallback — province_api (ไม่มี pdf_url) อ่าน deadline ที่ resolve เก็บไว้ใน DB
    # (เช่น ⭐ bid-open followup ที่ resolve ตอนเลื่อน B0→D0)
    if not bid_submit_date:
        d_date, d_time = _deadline_from_db(item["project_id"])
        if d_date:
            bid_submit_date, bid_submit_time = d_date, d_time
            log(f"  deadline จาก DB: {bid_submit_date} {bid_submit_time}")

    # Step 5: format message
    text = format_notification(
        project_id      = item["project_id"],
        province        = item.get("province") or "",
        announce_type   = item.get("announce_type") or "D0",
        budget          = budget,
        project_name    = item.get("project_name") or "",
        dept_name       = dept_name,
        deliver_day     = deliver_day,
        report_date     = report_date,
        bid_submit_date = bid_submit_date,
        bid_submit_time = bid_submit_time,
        is_backfill     = bool(item.get("is_backfill")),
        source_stage    = item.get("source_stage") or "api_enriched",
    )

    if dry_run:
        log("─── DRY RUN: message preview ───────────────────────────")
        for line_text in text.splitlines():
            log(f"  {line_text}")
        log(f"  → TO: {item['line_user_id']}")
        log("────────────────────────────────────────────────────────")
        # Release back to pending — dry run doesn't consume the item
        store.mark_delivery_result(
            queue_id    = item["id"],
            customer_id = item["customer_id"],
            project_id  = item["project_id"],
            status      = "failed",
            error       = "dry_run — not sent",
            error_type  = "retryable",
        )
        log("DRY RUN complete — item returned to pending queue")
        log("=== LINE Sender done (dry-run) ===")
        return

    # Step 5: send live
    full_name = _clean_project_name(item.get("project_name") or "") or item["project_id"]
    if (item.get("announce_type") or "") == "D0":
        # งานเปิดยื่นซองทุกงานที่ match → text ธรรมดา + intel + ลิงก์ติดตาม (signed token).
        # ลิงก์อยู่ในเนื้อข้อความ → เลื่อนกดงานเก่าได้ไม่หาย (แทน quick-reply ที่หายเมื่อหลายงาน).
        # N+108 follow-link. กัญจน์เลือก 2026-06-08
        link = build_follow_link(item["line_user_id"], item["project_id"])
        link_block = ("\n\n⭐ ติดตามงานนี้:\n" + link) if link else ""
        success, error_type, error_msg = send_line_push(
            token, item["line_user_id"], full_name + "\n" + text + link_block, quick_reply=None)
    else:
        _auth = _feedback_authority_ids()
        _with_fb = (not _auth) or (item["customer_id"] in _auth)
        flex = build_job_flex(
            project_id=item["project_id"],
            title=full_name,
            detail=text,
            doc_url=pdf_url,
            with_feedback=_with_fb,
        )
        alt_text = (full_name + " | " + text)[:400]
        success, error_type, error_msg = send_line_flex(token, item["line_user_id"], alt_text, flex)

    # Step 6: mark result
    store.mark_delivery_result(
        queue_id    = item["id"],
        customer_id = item["customer_id"],
        project_id  = item["project_id"],
        status      = "sent" if success else "failed",
        error       = error_msg,
        error_type  = error_type,
    )

    if success:
        log(f"SENT   queue_id={item['id']} → {item['line_user_id']}")
    elif error_type == "terminal":
        log(f"FAILED queue_id={item['id']} terminal error_type={error_type} msg={error_msg[:80]}")
    else:
        log(f"RETRY  queue_id={item['id']} retryable={error_type} msg={error_msg[:80]}")

    log("=== LINE Sender done ===")


if __name__ == "__main__":
    main()
