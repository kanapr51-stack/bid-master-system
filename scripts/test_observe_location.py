"""test_observe_location.py — สรุป distribution ของ location resolution (source/confidence)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")
import observe_location_resolution as obs


def test_summarize():
    res = [
        {"source": "geo", "location_confidence": "HIGH", "amphoe": "บ้านแพง"},
        {"source": "geo", "location_confidence": "LOW", "amphoe": "เซกา"},
        {"source": "tambon", "location_confidence": "HIGH", "amphoe": "บึงโขงหลง"},
        {"source": "province", "location_confidence": "LOW", "amphoe": None},
    ]
    s = obs.summarize(res)
    assert s["total"] == 4, s
    assert s["by_source"]["geo"] == 2 and s["by_source"]["province"] == 1, s
    assert s["by_confidence"]["HIGH"] == 2 and s["by_confidence"]["LOW"] == 2, s
    assert s["amphoe_resolved"] == 3, s   # ไม่นับ province (amphoe=None)
    assert s["amphoe_pct"] == 75.0, s
    print("✅ summarize")


def test_summarize_empty():
    s = obs.summarize([])
    assert s["total"] == 0 and s["amphoe_pct"] == 0.0, s
    print("✅ summarize empty")


if __name__ == "__main__":
    test_summarize()
    test_summarize_empty()
    print("ALL PASS observe_location")
