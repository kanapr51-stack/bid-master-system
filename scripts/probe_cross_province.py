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
    cnx = res.get("เชียงใหม่", "?")
    nkp = res.get("นครพนม", "?")
    bk = res.get("บึงกาฬ", "?")

    def _isdate(x): return bool(x) and x[0].isdigit()
    # control = กทม/เชียงใหม่ (เมืองใหญ่ มีงานเกือบทุกวันทำการ) — ใช้วัด "เราเรียก API ได้ไหม"
    control_ok = _isdate(bkk) or _isdate(cnx)
    national = max([x for x in (bkk, cnx) if _isdate(x)] or ["?"])   # eGP-wide latest

    # streak state (BMS_DATA_DIR) — track วันที่ eGP เงียบ (กทมไม่ขยับ) ติดกัน
    st_file = Path(os.environ.get("BMS_DATA_DIR", "/opt/bms/data")) / "crossprobe_state.json"
    try:
        st = json.loads(st_file.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    prev_national = st.get("national_latest", BASELINE)
    streak = int(st.get("quiet_streak", 0))

    if not control_ok:
        # กรณี (ก) — เรียก API ไม่ได้ทั้ง control → ระบบพังเงียบ รับงานทั้งประเทศไม่ได้
        verdict = ("🔴 CRITICAL — เรียก eGP ไม่ได้ทั้ง control (กทม+เชียงใหม่ ERR)\n"
                   "= ระบบเราพังเงียบ รับงานทั้งประเทศไม่ได้ (token/endpoint) → เจาะด่วน!")
        # ไม่แตะ streak (คนละแกน — นี่ระบบ ไม่ใช่ตลาด)
    elif _isdate(national) and national > prev_national:
        # eGP ขยับ (มีงานใหม่ทั้งประเทศ) → reset streak
        streak = 0
        if _isdate(max(nkp, bk)) and max(nkp, bk) >= prev_national and max(nkp, bk) > BASELINE:
            verdict = f"✅ HEALTHY — eGP ขึ้นงานใหม่ (ชาติ {national}) + นพ/บก ตามทัน ({max(nkp,bk)}) = ระบบถูกต้อง"
        else:
            verdict = (f"🟠 เช็ค — กทม/ชม มีงานใหม่ ({national}) แต่ นพ/บก ยัง {max(nkp,bk)}\n"
                       "= อาจ นพ/บก ไม่มีงานช่วงนี้จริง (จังหวัดเล็ก) หรือเราพลาด → ดูรอบหน้า/probe ซ้ำ")
        prev_national = national
    else:
        # control เรียกได้ แต่ eGP ไม่ขยับ → กรณี (ข) eGP ไม่มีงานใหม่จริง
        streak += 1
        if streak >= 3:
            verdict = (f"⚠️ เริ่มมีกลิ่น — eGP เงียบทั้งประเทศ {streak} วันติด (control เรียกได้ แต่ไม่มีงานใหม่)\n"
                       "3-4 วันขึ้นไป = ผิดปกติ → เช็ค eGP เปลี่ยน endpoint/budgetYear หรือ subtle fail")
        else:
            verdict = (f"🟡 eGP ไม่มีงานใหม่ (control เรียกได้ = เราไม่พัง) — เงียบ {streak} วัน "
                       "= ตลาดเงียบจริง ยังปกติ")

    # save state
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        st_file.write_text(json.dumps({
            "national_latest": prev_national, "quiet_streak": streak,
            "last_probe": _dt.now(_tz(_td(hours=7))).isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    msg = (
        f"🔭 Cross-Province Probe\n"
        f"  กรุงเทพ:  {bkk}\n  เชียงใหม่: {cnx}\n  นครพนม:   {nkp}\n  บึงกาฬ:   {bk}\n"
        f"\n{verdict}"
    )
    load_env(); t, ch = get_credentials()
    send(t, ch, msg)
    print(msg)


if __name__ == "__main__":
    main()
