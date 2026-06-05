"""test_bms_paths_heal.py — heal_legacy_state copy old→new + log, ไม่ทับ new ที่มีอยู่."""
import os, sys, tempfile, json
from pathlib import Path
d = tempfile.mkdtemp(); os.environ["BMS_DATA_DIR"] = d
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import bms_paths
legacy = bms_paths._REPO_ROOT / "data" / "_heal_test.json"
legacy.write_text('{"x":1}', encoding="utf-8")
try:
    healed = bms_paths.heal_legacy_state("_heal_test.json")   # new หาย → copy จาก old
    assert healed == ["_heal_test.json"], healed
    assert json.loads(bms_paths.runtime_path("_heal_test.json").read_text())["x"] == 1
    bms_paths.runtime_path("_heal_test.json").write_text('{"x":2}', encoding="utf-8")
    healed2 = bms_paths.heal_legacy_state("_heal_test.json")  # new มีแล้ว → ไม่ทับ
    assert healed2 == [], healed2
    assert json.loads(bms_paths.runtime_path("_heal_test.json").read_text())["x"] == 2
    print("✅ PASS heal_legacy_state")
finally:
    legacy.unlink(missing_ok=True)
