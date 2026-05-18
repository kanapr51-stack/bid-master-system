"""
customers_db.py — CRUD สำหรับ "customers" Google Sheet (Phase 2 SaaS pilot)

Schema:
  line_user_id     — LINE userId (primary key, จาก LINE Login or webhook)
  display_name     — ชื่อแสดง (จาก LINE profile)
  email            — optional
  phone            — optional
  จังหวัด           — comma-separated provinces
  อำเภอ            — comma-separated districts
  keywords         — extra keywords ที่ลูกค้าอยากเพิ่ม (comma)
  status           — trial | active | expired | cancelled
  registered_at    — ISO date
  expires_at       — ISO date (trial end / paid until)
  last_active_at   — ISO date (อัปเดตทุกครั้งที่เข้าเว็บหรือ LINE)
  notes            — admin notes
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

from sheets_client import open_sheet

SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
SHEET_NAME = "customers"

HEADERS = [
    "line_user_id",
    "display_name",
    "email",
    "phone",
    "จังหวัด",
    "อำเภอ",
    "keywords",
    "status",
    "registered_at",
    "expires_at",
    "last_active_at",
    "notes",
]


def get_or_create_sheet():
    """Open customers sheet — สร้างถ้ายังไม่มี (พร้อม headers)"""
    try:
        ws = open_sheet(SPREADSHEET_ID, SHEET_NAME)
        # Check headers
        existing = ws.row_values(1) if ws.row_count > 0 else []
        if not existing:
            ws.append_row(HEADERS, value_input_option="USER_ENTERED")
        return ws
    except Exception:
        # Create new worksheet
        gc = _get_client()
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="USER_ENTERED")
        return ws


def _get_client():
    from sheets_client import get_client
    return get_client()


def _row_to_dict(row: list) -> dict:
    return {h: (row[i] if i < len(row) else "") for i, h in enumerate(HEADERS)}


def _dict_to_row(d: dict) -> list:
    return [d.get(h, "") for h in HEADERS]


def list_all() -> list[dict]:
    """List all customers"""
    ws = get_or_create_sheet()
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    return [_row_to_dict(r) for r in rows[1:] if r and r[0]]


def get_by_line_id(line_user_id: str) -> dict | None:
    """Find customer by LINE userId"""
    if not line_user_id:
        return None
    for c in list_all():
        if c["line_user_id"] == line_user_id:
            return c
    return None


def upsert(data: dict) -> tuple[dict, bool]:
    """Create or update customer. Returns (customer_dict, is_new).
    Required: line_user_id
    """
    line_id = (data.get("line_user_id") or "").strip()
    if not line_id:
        raise ValueError("line_user_id required")

    ws = get_or_create_sheet()
    rows = ws.get_all_values()
    now = datetime.now().isoformat(timespec="seconds")

    # Find existing
    for i, r in enumerate(rows[1:], start=2):
        if r and r[0] == line_id:
            existing = _row_to_dict(r)
            merged = {**existing, **{k: v for k, v in data.items() if v != ""}}
            merged["last_active_at"] = now
            ws.update(
                range_name=f"A{i}:{chr(ord('A') + len(HEADERS) - 1)}{i}",
                values=[_dict_to_row(merged)],
                value_input_option="USER_ENTERED",
            )
            return merged, False

    # New
    new = {h: "" for h in HEADERS}
    new.update(data)
    new["line_user_id"] = line_id
    if not new.get("status"):
        new["status"] = "trial"
    if not new.get("registered_at"):
        new["registered_at"] = now
    if not new.get("expires_at"):
        # 14-day trial by default
        new["expires_at"] = (datetime.now() + timedelta(days=14)).isoformat(timespec="seconds")
    new["last_active_at"] = now

    ws.append_row(_dict_to_row(new), value_input_option="USER_ENTERED")
    return new, True


def update_settings(line_user_id: str, *,
                    provinces: list[str] | None = None,
                    districts: list[str] | None = None,
                    keywords: list[str] | None = None,
                    display_name: str | None = None,
                    email: str | None = None,
                    phone: str | None = None) -> dict | None:
    """Convenience: update customer settings"""
    data = {"line_user_id": line_user_id}
    if provinces is not None:
        data["จังหวัด"] = ", ".join(provinces)
    if districts is not None:
        data["อำเภอ"] = ", ".join(districts)
    if keywords is not None:
        data["keywords"] = ", ".join(keywords)
    if display_name is not None:
        data["display_name"] = display_name
    if email is not None:
        data["email"] = email
    if phone is not None:
        data["phone"] = phone
    customer, _ = upsert(data)
    return customer


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="create customers sheet (idempotent)")
    ap.add_argument("--list", action="store_true", help="list all customers")
    ap.add_argument("--get", help="get customer by line_user_id")
    ap.add_argument("--seed-me", help="seed คุณกัญจน์ as test customer (pass userId)")
    args = ap.parse_args()

    if args.init:
        get_or_create_sheet()
        print(f"✅ Sheet '{SHEET_NAME}' พร้อมใช้งาน (มี headers: {len(HEADERS)} cols)")
    elif args.list:
        cs = list_all()
        print(f"Total customers: {len(cs)}")
        for c in cs:
            print(f"  {c['line_user_id']}: {c['display_name']} | {c['จังหวัด']} | {c['status']}")
    elif args.get:
        c = get_by_line_id(args.get)
        print(json.dumps(c, ensure_ascii=False, indent=2) if c else "Not found")
    elif args.seed_me:
        customer, is_new = upsert({
            "line_user_id": args.seed_me,
            "display_name": "กัญจน์ (owner)",
            "จังหวัด": "นครพนม, บึงกาฬ",
            "อำเภอ": "บ้านแพง, บึงโขงหลง",
            "keywords": "",
            "status": "active",
            "notes": "owner — unlimited",
            "expires_at": "2099-12-31",
        })
        print(f"{'➕ Created' if is_new else '🔄 Updated'}: {customer}")
    else:
        ap.print_help()
