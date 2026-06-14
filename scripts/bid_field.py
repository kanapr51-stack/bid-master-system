"""bid_field.py — ตรวจ "เจ้าใหญ่ขาดลอย" จาก full-field bids (2B). เสนอ 2 ฉากทัศน์ในการ์ด D0.
graceful gate (โชว์เฉพาะ scope ที่ข้อมูลพอ+มีโครงสร้างขาดลอย). ดู spec 2026-06-14-dominant-detection-2b."""
import sqlite3, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import COMPETITIVE_SET

MIN_AUCTIONS = 5       # scope ต้องมี ≥ นี้ ถึงวิเคราะห์
MIN_APPEAR = 3         # บริษัทปรากฏ ≥ นี้ ถึง "ระบุชื่อ"
WIN_FRACTION = 0.5     # ชนะ ≥ ครึ่งที่ลง
LANDSLIDE_GAP = 10.0   # percentage points (ผู้ชนะขาดที่2)
LANDSLIDE_RATE = 0.30  # Tier2: ≥30% ของ auctions เป็น landslide
DISC_MAX = 60.0        # ตัด outlier disc (unit-price เพี้ยน)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _winner_idx(auction):
    """index ผู้ชนะ: is_winner ก่อน, fallback disc สูงสุด."""
    for i, (_n, _d, w) in enumerate(auction):
        if w:
            return i
    return max(range(len(auction)), key=lambda i: auction[i][1])


def analyze_field(auctions: list) -> dict:
    """tiered detection. auctions = [ [(name, disc_pct, is_winner)] ].
    คืน {tier:0|1|2, n_auctions, pack_disc_med, dominant:{name,show_rate,win_disc_med,win_gap_med}|None,
         landslide_gap_med}."""
    auctions = [a for a in auctions if len(a) >= 2]
    n = len(auctions)
    base = {"tier": 0, "n_auctions": n, "pack_disc_med": None,
            "dominant": None, "landslide_gap_med": None}
    if n < MIN_AUCTIONS:
        return base
    pack_discs, gaps = [], []
    appear, wins = defaultdict(int), defaultdict(int)
    win_disc, win_gap = defaultdict(list), defaultdict(list)
    for a in auctions:
        wi = _winner_idx(a)
        wname, wdisc, _ = a[wi]
        others = [d for j, (_n, d, _w) in enumerate(a) if j != wi]
        pack_discs += others
        second = max(others) if others else wdisc
        gap = wdisc - second
        gaps.append(gap)
        seen = set()
        for (nm, _d, _w) in a:
            if nm and nm not in seen:        # นับ 1 บริษัท/auction
                appear[nm] += 1
                seen.add(nm)
        if wname:
            wins[wname] += 1
            win_disc[wname].append(wdisc)
            win_gap[wname].append(gap)
    base["pack_disc_med"] = _median(pack_discs)
    landslide = [g for g in gaps if g > LANDSLIDE_GAP]
    # Tier 1: named dominant
    cands = []
    for name, ap in appear.items():
        if ap >= MIN_APPEAR and wins[name] / ap >= WIN_FRACTION:
            wg = _median(win_gap[name])
            if wg is not None and wg > LANDSLIDE_GAP:
                cands.append((ap, wg, name))
    if cands:
        cands.sort(reverse=True)             # appear มากสุดก่อน, เสมอ→gap มากกว่า (ไม่ tiebreak ด้วยชื่อ)
        ap, wg, name = cands[0]
        base["tier"] = 1
        base["dominant"] = {"name": name, "show_rate": ap / n,
                            "win_disc_med": _median(win_disc[name]), "win_gap_med": wg}
        return base
    # Tier 2: structural landslide
    if len(landslide) / n >= LANDSLIDE_RATE:
        base["tier"] = 2
        base["landslide_gap_med"] = _median(landslide)
    return base


def _short(name):
    """ย่อชื่อ: ห้างหุ้นส่วนจำกัด→หจก. · บริษัท→บ."""
    return name.replace("ห้างหุ้นส่วนจำกัด", "หจก.").replace("บริษัท", "บ.").strip()


def field_lines(fr: dict, budget_now) -> list:
    """บรรทัดการ์ดเจ้าใหญ่ (baht ตาม budget งานปัจจุบัน). [] ถ้า tier0/ข้อมูลน้อย/ไม่มี budget."""
    if not fr or fr.get("tier", 0) == 0 or fr.get("pack_disc_med") is None or not budget_now:
        return []
    b = float(budget_now)

    def price(disc):
        return round(b * (1 - disc / 100.0))

    pack = price(fr["pack_disc_med"])
    if fr["tier"] == 1:
        d = fr["dominant"]
        nm = _short(d["name"])
        sr = d["show_rate"] * 100
        win = price(d["win_disc_med"])
        risk = (f"   ⚠️ {nm} มาบ่อย ({sr:.0f}%) — ยื่นตื้นมีความเสี่ยง" if d["show_rate"] >= 0.5
                else f"   {nm} ลงไม่บ่อย ({sr:.0f}%) — มีโอกาสยื่นตื้น")
        return [
            f"🏆 สนามนี้มีเจ้าใหญ่: {nm} (ลง ~{sr:.0f}% ของงาน · ชนะขาดลอยเฉลี่ย {d['win_gap_med']:.0f}%)",
            f"   • ถ้า {nm} มา → ต้องยื่นต่ำกว่า ~{win:,.0f} (ระดับเจ้าใหญ่) ถึงแซง (กำไรบาง)",
            f"   • ถ้าไม่มา → กลุ่มที่เหลืออยู่ ~{pack:,.0f} → ยื่นต่ำกว่ากลุ่มนิดเดียวก็ชนะ (กำไรงาม)",
            risk,
        ]
    return [    # tier 2
        f"🏆 สนามนี้ผู้ชนะมักขาดลอย ~{fr['landslide_gap_med']:.0f}% (ไม่มีเจ้าเด่นชัด)",
        f"   • กลุ่มหลักอยู่ ~{pack:,.0f} → ถ้าคู่แข่งดุไม่มา ยื่นต่ำกว่ากลุ่มก็ชนะ",
    ]
