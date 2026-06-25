"""test_is_cancelled.py — predicate ยกเลิก (extract จาก classifier) + regression classify_by_stepid."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from Sebastian_Classifier import is_cancelled, classify_by_stepid


# ── is_cancelled: 3 สัญญาณ ──────────────────────────────────────────────
# gold: projectStatus == "R"
ok, note = is_cancelled("W01", "R", "W0")
assert ok and note == "ยกเลิกหลังประมูล (W01)", (ok, note)

# secondary: announce D1 / W1
assert is_cancelled("S01", "", "D1")[0] is True, "D1 ควรยกเลิก"
assert is_cancelled("W03", "", "W1")[0] is True, "W1 ควรยกเลิก"

# secondary note ตาม stage
assert is_cancelled("S01", "", "D1")[1] == "ยกเลิกระหว่างยื่นซอง (S01)", is_cancelled("S01", "", "D1")
assert is_cancelled("Q01", "R", "")[1] == "ยกเลิกตั้งแต่ขั้นวางแผน (Q01)", is_cancelled("Q01", "R", "")
assert is_cancelled("U03", "R", "")[1] == "ยกเลิกระหว่างเตรียม TOR (U03)", is_cancelled("U03", "R", "")

# B-prefix ล้วน (ไม่ R/D1/W1) → True, note="" (ตาม path LETTER_TO_SHEET เดิม)
ok, note = is_cancelled("B01", "", "D0")
assert ok is True and note == "", (ok, note)

# ปกติ → False
assert is_cancelled("S01", "", "D0") == (False, ""), is_cancelled("S01", "", "D0")
assert is_cancelled("", "", "") == (False, ""), is_cancelled("", "", "")
assert is_cancelled("M03", "", "D0") == (False, ""), is_cancelled("M03", "", "D0")
print("✅ is_cancelled 3 สัญญาณ + note + negative")


# ── regression: classify_by_stepid พฤติกรรมเดิมต้องไม่เปลี่ยน ──────────────
# R → cancelled_jobs พร้อม note
assert classify_by_stepid("S01", "R", "D0", False) == ("cancelled_jobs", "ยกเลิกระหว่างยื่นซอง (S01)")
# D1 secondary → cancelled
assert classify_by_stepid("W03", "", "D1", False)[0] == "cancelled_jobs"
# B-prefix + has_winner → awarded (path has_winner มาก่อน letter routing — ต้องไม่ใช่ cancelled)
assert classify_by_stepid("B01", "", "D0", True) == ("awarded_jobs", ""), classify_by_stepid("B01", "", "D0", True)
# B-prefix ล้วน ไม่ winner → cancelled_jobs (LETTER_TO_SHEET)
assert classify_by_stepid("B01", "", "D0", False)[0] == "cancelled_jobs"
# active ปกติ
assert classify_by_stepid("S01", "", "D0", False)[0] == "active_bidding"
print("✅ classify_by_stepid regression ผ่าน (พฤติกรรมเดิมไม่เปลี่ยน)")

print("✅ ALL PASS test_is_cancelled")
