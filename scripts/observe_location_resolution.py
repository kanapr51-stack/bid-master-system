"""observe_location_resolution.py — สรุป distribution ของ location resolution (source/confidence)
ของงานเป้าหมายที่ qualify (ที่ intel จะ render). compute สด จาก resolve_location — ไม่พึ่ง log,
ไม่ยิง API (read-only DB + geo in-memory, ปลอดภัย schedule ได้). ใช้ตัดสินใจ Phase B + calibrate.

รันบน VPS:  python observe_location_resolution.py [--discord]
"""
import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent)); sys.stdout.reconfigure(encoding="utf-8")


def summarize(resolutions: list) -> dict:
    """นับ distribution ของ source/confidence + % ที่ resolve อำเภอได้ (ไม่ใช่ province degrade)."""
    total = len(resolutions)
    by_source = dict(Counter(r["source"] for r in resolutions))
    by_conf = dict(Counter(r["location_confidence"] for r in resolutions))
    amphoe_resolved = sum(1 for r in resolutions if r.get("amphoe"))
    return {
        "total": total,
        "by_source": by_source,
        "by_confidence": by_conf,
        "amphoe_resolved": amphoe_resolved,
        "amphoe_pct": round(amphoe_resolved * 100.0 / total, 1) if total else 0.0,
    }


def collect(conn) -> list:
    """resolve_location ทุกงานเป้าหมายที่ qualify + match work-type (universe ที่ intel ทำงาน)."""
    import cgd_intel as ci
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT pl.project_id, ps.province, ps.project_name, ps.dept_name
        FROM project_locations pl
        JOIN projects_seen ps ON ps.project_id = pl.project_id
        WHERE pl.qualification_status IN ('enqueued', 'suppressed_preview')
    """).fetchall()
    out = []
    for r in rows:
        if not ci.match_keywords(r["project_name"] or ""):
            continue   # intel ทำเฉพาะงานหมวด match
        loc = ci.resolve_location(r["project_id"], r["project_name"] or "",
                                  r["dept_name"] or "", r["province"] or "", conn)
        out.append(loc)
    return out


def format_report(s: dict) -> str:
    lines = [f"📊 Location Resolution (intel universe) — {s['total']} งาน"]
    lines.append(f"🎯 resolve อำเภอได้ {s['amphoe_resolved']}/{s['total']} ({s['amphoe_pct']}%)")
    order = ["geo", "tambon", "dept", "province", "moi"]
    src = s["by_source"]
    lines.append("ชั้นที่ใช้: " + " · ".join(f"{k}={src[k]}" for k in order if k in src))
    conf = s["by_confidence"]
    lines.append("confidence: " + " · ".join(f"{k}={conf[k]}" for k in ("HIGH", "MEDIUM", "LOW") if k in conf))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--discord", action="store_true", help="ส่งสรุปเข้า Discord")
    a = ap.parse_args(argv)
    from Sebastian_Customer_DB import get_connection
    with get_connection() as conn:
        s = summarize(collect(conn))
    report = format_report(s)
    print(report)
    if a.discord:
        try:
            from Sebastian_Discord_Notify import load_env, get_credentials, send
            load_env(); tok, ch = get_credentials()
            send(tok, ch, "🔭 Observe " + report)
        except Exception as e:
            print(f"discord ล้มเหลว: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
