"""analyze_center_monitor.py — สรุป B″ center-error breadcrumb (observe-only monitor).

อ่าน winrate_center_monitor.ndjson → ตอบ: เมื่อ ladder ผ่อน, center บน "อำเภอ" ต่างจาก "จังหวัด"
มากพอจะคุ้มทำ B″ (center-intermediate) ไหม. directional — N เล็ก ดูเป็นแนวโน้ม.

  BMS_DATA_DIR=/opt/bms/data python3 scripts/analyze_center_monitor.py
"""
import json
import os
import sys


def _pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    i = (len(s) - 1) * (p / 100.0)
    lo = int(i)
    frac = i - lo
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + frac * (s[hi] - s[lo])


def summarize(records: list) -> dict:
    """รวม breadcrumb records → distribution. delta stats คิดเฉพาะ record ที่ amphoe_eligible
    (= อำเภอมี full-field ≥ MIN_N_AUCTIONS → B″ จะ center บนอำเภอได้จริง)."""
    by_conf = {}
    for r in records:
        c = r.get("conf", "?")
        by_conf[c] = by_conf.get(c, 0) + 1
    elig = [r for r in records if r.get("amphoe_eligible")]
    deltas = [r.get("delta_mean", 0.0) for r in elig]
    ge2 = [d for d in deltas if d >= 2]
    return {
        "total": len(records),
        "by_conf": by_conf,
        "amphoe_eligible": len(elig),
        "delta_median": _pct(deltas, 50) if deltas else 0.0,
        "delta_p90": _pct(deltas, 90) if deltas else 0.0,
        "pct_delta_ge2": (len(ge2) / len(deltas) * 100.0) if deltas else 0.0,
    }


def _load(path: str) -> list:
    recs = []
    if not os.path.exists(path):
        return recs
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return recs


def render(sm: dict) -> str:
    L = ["📐 B″ Center-Error Monitor", ""]
    L.append(f"records ทั้งหมด: {sm['total']}")
    L.append("ผ่อนไป (conf): " + ", ".join(f"{k}={v}" for k, v in sm["by_conf"].items()) or "—")
    L.append(f"อำเภอ eligible (full-field ≥3): {sm['amphoe_eligible']}")
    L.append("")
    L.append("Δ center (อำเภอ vs จังหวัด) — เฉพาะ eligible:")
    L.append(f"  median: {sm['delta_median']:.1f} ผู้ยื่น · p90: {sm['delta_p90']:.1f}")
    L.append(f"  %ที่ Δ≥2: {sm['pct_delta_ge2']:.0f}%  ← Δ≥2 = B″ จะเปลี่ยนตารางจริง")
    L.append("")
    if sm["amphoe_eligible"] < 5:
        L.append("⚠️ eligible < 5 — ยังตัดสิน B″ ไม่ได้ (ปล่อย monitor สะสมต่อ)")
    elif sm["pct_delta_ge2"] >= 50:
        L.append("→ Δ ใหญ่บ่อย: B″ (center-intermediate) น่าจะคุ้ม — พิจารณา implement")
    else:
        L.append("→ Δ เล็กเป็นส่วนใหญ่: จังหวัด center ใกล้พอ — B″ ยังไม่คุ้ม")
    return "\n".join(L)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # กัน Windows console cp1252 (VPS Linux ไม่ต้อง)
    except Exception:
        pass
    path = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(os.environ.get("BMS_DATA_DIR") or
                              os.path.join(os.path.dirname(__file__), "..", "data"),
                              "winrate_center_monitor.ndjson"))
    print(render(summarize(_load(path))))


if __name__ == "__main__":
    main()
