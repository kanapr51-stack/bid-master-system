"""job_followups.py — ตัดสินว่าใครต้องแจ้ง stage transition ของงานที่ติดตาม (⭐).
ใช้โดย Enrichment_Worker (B0→D0) + Winner_Poller (→W0). pure logic เหนือ followed_jobs.
"""
_STAGE_ORDER = {"B0": 0, "D0": 1, "W0": 2}


def followers_due_for_stage(store, project_id: str, new_stage: str) -> list:
    """customer_ids ที่ติดตาม project นี้ (active) + ยังไม่แจ้งถึง new_stage
    (last_stage_notified < new_stage ตามลำดับชีวิตงาน). กัน dedup ข้าม stage."""
    nv = _STAGE_ORDER.get(new_stage, 99)
    return [f["customer_id"] for f in store.get_active_follows()
            if f["project_id"] == project_id
            and _STAGE_ORDER.get(f["last_stage_notified"] or "", -1) < nv]


def bid_open_followups(active_follows: list, current_stage_by_pid: dict) -> list:
    """[(customer_id, project_id)] ที่ติดดาวตอน B (รับฟังฯ) + งานเลื่อนเป็น D (ประมูล) แล้ว
    + ยังไม่แจ้ง D. pure — caller (enrichment) สร้าง current_stage_by_pid จาก projects_seen."""
    out = []
    for f in active_follows:
        if (f["last_stage_notified"] or "").startswith("B") \
                and current_stage_by_pid.get(f["project_id"], "").startswith("D"):
            out.append((f["customer_id"], f["project_id"]))
    return out
