"""probe_cross_province.py — one-shot cross-province baseline check (2026-06-02)

เทียบ announceDate ล่าสุด: control ใหญ่ (กทม/เชียงใหม่) vs เรา (นพ/บก).
verdict → Discord. ตอบคำถามกัญจน์: eGP ขึ้นงานสัปดาห์ใหม่หรือยัง + นพ/บก ตามทันไหม

logic:
  กทม ขยับ (latest > 05-29) + นพ/บก ตาม      → ✅ healthy (lag resolve, ระบบทัน)
  กทม ขยับ แต่ นพ/บก ยัง 05-29               → ⚠️ เรา lag/พลาด (เจาะ)
  กทม ยัง 05-29                               → eGP ยังไม่ขึ้น (lag ทั้งประเทศ, รอต่อ)
"""
import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import Sebastian_Province_Discovery as d
from Sebastian_Discord_Notify import load_env, get_credentials, send

BASELINE = "2026-05-29"   # latest ทั้งประเทศ ณ จันทร์ 06-01 (ก่อน probe นี้)
PROVS = [("100000", "กรุงเทพ"), ("500000", "เชียงใหม่"),
         ("480000", "นครพนม"), ("380000", "บึงกาฬ")]


def latest_date(tok: str, moi: str, prov: str) -> str:
    try:
        items = d.fetch_page(tok, moi, "2569", 1)
        dates = [d.normalize(it, prov)["announce_date"] for it in items[:8] if it]
        dates = [x for x in dates if x]
        return max(dates) if dates else "?"
    except Exception:
        return "ERR"


def main():
    tok_file = Path(os.environ.get("BMS_DATA_DIR", "/opt/bms/data")) / "token_state.json"
    try:
        tok = json.loads(tok_file.read_text(encoding="utf-8")).get("token")
    except Exception as e:
        tok = None
    if not tok:
        load_env(); t, ch = get_credentials()
        send(t, ch, "🔭 cross-province probe: ❌ token โหลดไม่ได้ — เช็ค token harvest")
        return

    res = {}
    for moi, prov in PROVS:
        res[prov] = latest_date(tok, moi, prov)
        time.sleep(1.5)

    bkk = res.get("กรุงเทพ", "?")
    nkp = res.get("นครพนม", "?")
    bk = res.get("บึงกาฬ", "?")
    ours_max = max([x for x in (nkp, bk) if x and x[0].isdigit()] or ["?"])

    egp_moved = bkk[0].isdigit() and bkk > BASELINE
    ours_moved = ours_max != "?" and ours_max > BASELINE

    if egp_moved and ours_moved:
        verdict = "✅ HEALTHY — eGP ขึ้นงานสัปดาห์ใหม่ + นพ/บก ตามทัน (lag resolve, ระบบถูกต้อง)"
    elif egp_moved and not ours_moved:
        verdict = "⚠️ ALERT — กทมขยับแต่ นพ/บก ยังค้าง 05-29 → เริ่มมีกลิ่น เจาะด่วน"
    else:
        verdict = "🟡 eGP ยังไม่ขึ้นงานสัปดาห์ใหม่ทั้งประเทศ (กทมยังค้าง) — lag ต่อ ยังไม่ใช่ปัญหาเรา"

    msg = (
        f"🔭 Cross-Province Probe (เทียบ baseline {BASELINE})\n"
        f"  กรุงเทพ:  {bkk}\n"
        f"  เชียงใหม่: {res.get('เชียงใหม่','?')}\n"
        f"  นครพนม:   {nkp}\n"
        f"  บึงกาฬ:   {bk}\n"
        f"\n{verdict}"
    )
    load_env(); t, ch = get_credentials()
    send(t, ch, msg)
    print(msg)


if __name__ == "__main__":
    main()
