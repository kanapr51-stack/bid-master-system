"""Re-extract winner จาก raw_json (ไม่ fetch ใหม่) — แก้ column-shift L-006 รอบ 2.
หลักการ: ชื่อผู้ชนะ field ถ้าเป็น 'วันที่' = row โดน shift → winner จริงอยู่ ละติจูดโครงการ.
detect วันที่/ตัวเลข robust กว่า marker scan (จับ ครัวอิ่มสุข, นายX ติดกัน, การไฟฟ้าฯ ได้)."""
import sqlite3, json, sys, re
sys.stdout.reconfigure(encoding="utf-8")

DB = "data/winner_history.db"
THAI_MONTH = "(ม\\.ค\\.|ก\\.พ\\.|มี\\.ค\\.|เม\\.ย\\.|พ\\.ค\\.|มิ\\.ย\\.|ก\\.ค\\.|ส\\.ค\\.|ก\\.ย\\.|ต\\.ค\\.|พ\\.ย\\.|ธ\\.ค\\.)"
DATE_RE = re.compile(r"^\d{1,2}\s*" + THAI_MONTH + r"\s*\d{2,4}$")
NUM_RE = re.compile(r"^[\d.,\-/\s]+$")
# คำที่บอกว่าเป็น "ผู้ชนะ" แม้ไม่มี prefix บริษัท (กันเผลอหยิบ field ผิด)
ORG_HINT = ("บริษัท", "ห้าง", "หจก", "ร้าน", "นาย", "นาง", "น.ส.", "กิจการร่วมค้า",
            "สหกรณ์", "วิสาหกิจ", "คณะบุคคล", "องค์การ", "การไฟฟ้า", "การประปา",
            "ครัว", "มูลนิธิ", "สมาคม", "กลุ่ม", "โรงงาน", "อู่", "คลินิก", "หมอ")


def is_date(s): return bool(DATE_RE.match(s.strip()))
def is_num(s): return bool(s.strip()) and bool(NUM_RE.match(s.strip()))


def winner_of(r):
    # 1) ชื่อผู้ชนะ ตรง ถ้าไม่ใช่วันที่/ตัวเลข = non-shifted
    w = str(r.get("ชื่อผู้ชนะ") or "").strip()
    if w and not is_date(w) and not is_num(w):
        return w
    # 2) shifted → winner อยู่ ละติจูดโครงการ
    lat = str(r.get("ละติจูดโครงการ") or "").strip()
    if lat and not is_date(lat) and not is_num(lat):
        return lat
    # 3) fallback: field ใดก็ได้ที่มี hint คำผู้ชนะ (ยกเว้น meta)
    skip = {"ชื่อโครงการ", "ชื่อหน่วยงาน", "ชื่อหน่วยงานย่อย", "ชื่อประเภทโครงการ",
            "วิธีจัดซื้อฯ", "กลุ่มวิธีจัดซื้อฯ", "จังหวัด", "เขต/อำเภอ", "แขวง/ตำบล"}
    for k, v in r.items():
        if k in skip:
            continue
        s = str(v).strip()
        if s and not is_date(s) and not is_num(s) and any(h in s for h in ORG_HINT):
            return s
    return ""


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    rows = c.execute("SELECT project_id, raw_json FROM winner_history").fetchall()
    updates = []
    for pid, raw in rows:
        updates.append((winner_of(json.loads(raw)), pid))
    conn.executemany("UPDATE winner_history SET winner=? WHERE project_id=?", updates)
    conn.commit()
    tot = len(rows)
    found = sum(1 for w, _ in updates if w)
    print(f"re-extract: {tot:,} rows | มีชื่อผู้ชนะ: {found:,} ({found/tot*100:.1f}%)")
    # sample ตรวจ
    print("\n=== sample 8 ผู้ชนะหลัง re-extract ===")
    for (w,) in c.execute("SELECT winner FROM winner_history WHERE winner!='' ORDER BY RANDOM() LIMIT 8"):
        print("  ", w[:50])
    # ที่ยังว่าง
    still = c.execute("SELECT COUNT(*) FROM winner_history WHERE winner=''").fetchone()[0]
    print(f"\nยังว่าง: {still:,}")
    for (raw,) in c.execute("SELECT raw_json FROM winner_history WHERE winner='' LIMIT 4"):
        r = json.loads(raw)
        print(f"   ชื่อผู้ชนะ='{r.get('ชื่อผู้ชนะ')}' ละติจูด='{r.get('ละติจูดโครงการ')}' ลองจิจูด='{r.get('ลองจิจูดโครงการ')}'")


if __name__ == "__main__":
    main()
