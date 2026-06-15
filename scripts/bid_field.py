"""bid_field.py — "เจ้าตลาด" intel จาก full-field bids (2B). ใครชนะ scope นี้บ่อย + ลดเฉลี่ยเท่าไหร่.
v2 pivot (evidence 2026-06-14): landslide หายาก (5-10%/scope) แต่มีเจ้าตลาดชัด (ชนะ 48-83% ชิดๆ)
→ จับด้วย win-frequency ไม่ใช่ landslide-gap. graceful gate. ดู spec 2026-06-14-dominant-detection-2b."""
import sqlite3, sys, os, math, logging
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import COMPETITIVE_SET, recency_weight

_log = logging.getLogger(__name__)

MIN_AUCTIONS = 5        # scope ต้องมี ≥ นี้ ถึงวิเคราะห์
MIN_APPEAR = 5          # บริษัทต้องลง ≥ นี้ ถึงนับเป็นเจ้าตลาด (ตัดฟลุ๊ค ลง1-2ชนะหมด)
LEADER_WIN_RATE = 0.40  # ชนะ ≥ 40% ของที่ลง (สุ่ม ~17% ที่ 5.9 ราย → 40% = เด่นจริง)
DISC_MAX = 60.0         # ตัด outlier disc (unit-price เพี้ยน)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _quantile(sorted_vals, q):
    """ค่าที่ percentile q (0..1) — linear interpolation. sorted_vals เรียงแล้ว, ไม่ว่าง."""
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
    return sorted_vals[lo]


def _weighted_quantile(pairs, q):
    """ค่าที่ cumulative-weight quantile q (0..1) — Hazen plotting position บนน้ำหนักสะสม.
    pairs = [(value, weight)] · weight>0. น้ำหนักเท่ากัน → ใกล้ median ปกติ. ว่าง → 0."""
    sp = sorted(pairs)
    if not sp:
        return 0.0
    total = sum(w for _v, w in sp)
    if total <= 0:
        return sp[0][0]
    pts, cum = [], 0.0
    for v, w in sp:
        pts.append(((cum + w / 2.0) / total, v))    # Hazen: กึ่งกลางช่วงน้ำหนัก
        cum += w
    if q <= pts[0][0]:
        return pts[0][1]
    if q >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        p0, v0 = pts[i - 1]
        p1, v1 = pts[i]
        if q <= p1:
            frac = (q - p0) / (p1 - p0) if p1 > p0 else 0.0
            return v0 + frac * (v1 - v0)
    return pts[-1][1]


def winrate_grid(auctions, budget, targets=(75, 50, 25)):
    """ตาราง win% conditional ตามจำนวนผู้ยื่น (B.1 — เลือกราคาแถวจาก win เป้าหมาย).
    ราคาแต่ละแถว = ราคาที่ให้ win% = target ที่สนามปกติ (k_mid) จาก inverse-CDF ของ bid จริง.
    win% คอลัมน์ k = target^(k/k_mid) (ราคา=ข้อมูลจริง · การกระจายข้ามคอลัมน์=โมเดล F_bid^k).
    auctions = [[(name,disc,is_winner)]] · budget = งบงานปัจจุบัน.
    คืน {ns, rows, n_mean, n_sd, n_auctions, n_bids, budget} หรือ None ถ้า gate ไม่ผ่าน/ราคายุบ."""
    auctions = [a for a in auctions if len(a) >= 2]
    n_auctions = len(auctions)
    try:
        bud = float(budget)
    except (TypeError, ValueError):
        bud = 0
    if n_auctions < MIN_AUCTIONS or bud <= 0:
        return None
    bids = sorted(d for a in auctions for (_n, d, _w) in a)
    if not bids:
        return None
    sizes = [len(a) for a in auctions]
    n_mean = sum(sizes) / n_auctions
    var = sum((s - n_mean) ** 2 for s in sizes) / (n_auctions - 1)   # sample variance
    n_sd = math.sqrt(var)
    raw = [round(n_mean - n_sd), round(n_mean), round(n_mean + n_sd)]
    ns = []
    for k in raw:                                  # clamp ≥2 + dedupe รักษาลำดับ
        k = max(2, k)
        if k not in ns:
            ns.append(k)
    k_mid = ns[len(ns) // 2]                        # คอลัมน์กลาง = สนามปกติ (≈ mean)
    rows, seen_price = [], set()
    for t in targets:                              # ราคาที่ให้ win=t ที่ k_mid (invert F_bid)
        tf = t / 100.0
        disc = _quantile(bids, tf ** (1.0 / k_mid))     # F_bid(disc) = tf^(1/k_mid)
        price = round(bud * (1 - disc / 100.0))
        if price in seen_price:                         # กันราคาซ้ำ (สนามแคบ)
            continue
        seen_price.add(price)
        rows.append((price, [round(tf ** (k / k_mid) * 100) for k in ns]))
    if len(rows) < 2:                              # ราคายุบ (<2 แถว) → ไม่มีประโยชน์ → fallback การ์ดเดิม
        return None
    rows.sort()                                     # ราคาน้อย→มาก (ดุ→กำไร)
    return {"ns": ns, "rows": rows, "n_mean": n_mean, "n_sd": n_sd,
            "n_auctions": n_auctions, "n_bids": len(bids), "budget": bud}


def winrate_lines(grid, basis="") -> list:
    """render ตาราง win% (pure). [] ถ้า grid None.
    คอลัมน์ = จำนวนผู้ยื่น (mean±SD) · แถว = ราคา a/b/c · footer = ค่าเฉลี่ย + sample size."""
    if not grid:
        return []
    ns, rows = grid["ns"], grid["rows"]
    lines = [f"💵 แนะนำราคายื่น (งบ {grid['budget']:,.0f}) — โอกาสชนะตามจำนวนผู้ยื่น"]
    lines.append("   ผู้ยื่น →   " + "  ".join(f"{k}ราย".rjust(6) for k in ns))
    for price, ws in rows:
        cells = "  ".join(f"{w}%".rjust(6) for w in ws)
        lines.append(f"   {price:>10,.0f}  {cells}")
    sd_txt = f" (±{round(grid['n_sd'])})" if len(ns) > 1 else ""
    lines.append(f"   📊 สนามนี้เฉลี่ย {round(grid['n_mean'])} ผู้ยื่น{sd_txt} · อิง{basis}")
    lines.append(f"   📈 จาก {grid['n_auctions']} งานที่มีข้อมูลผู้ยื่นครบ · {grid['n_bids']} ราย")
    lines.append("   * คอลัมน์ตรงค่าเฉลี่ย = เป้า 75/50/25 · ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ")
    return lines


def _winner_idx(auction):
    """index ผู้ชนะ: is_winner ก่อน, fallback disc สูงสุด."""
    for i, (_n, _d, w) in enumerate(auction):
        if w:
            return i
    return max(range(len(auction)), key=lambda i: auction[i][1])


def analyze_field(auctions: list) -> dict:
    """market-leader detection (win-frequency). auctions = [ [(name, disc_pct, is_winner)] ].
    คืน {tier:0|1, n_auctions, leaders:[{name,win_rate,wins,appears,win_disc_med}]} — top 2 เรียงชนะมากสุด.
    tier 1 = มีเจ้าตลาด (ลง≥MIN_APPEAR ∧ ชนะ≥LEADER_WIN_RATE) · tier 0 = ไม่มี/ข้อมูลน้อย."""
    auctions = [a for a in auctions if len(a) >= 2]
    n = len(auctions)
    base = {"tier": 0, "n_auctions": n, "leaders": []}
    if n < MIN_AUCTIONS:
        return base
    appear, wins, win_disc = defaultdict(int), defaultdict(int), defaultdict(list)
    for a in auctions:
        wi = _winner_idx(a)
        wname, wdisc, _ = a[wi]
        seen = set()
        for (nm, _d, _w) in a:
            if nm and nm not in seen:        # นับ 1 บริษัท/auction
                appear[nm] += 1
                seen.add(nm)
        if wname:
            wins[wname] += 1
            win_disc[wname].append(wdisc)
    leaders = []
    for name, ap in appear.items():
        if ap >= MIN_APPEAR and wins[name] / ap >= LEADER_WIN_RATE:
            leaders.append({"name": name, "win_rate": wins[name] / ap, "wins": wins[name],
                            "appears": ap, "win_disc_med": _median(win_disc[name])})
    if leaders:
        leaders.sort(key=lambda L: (-L["wins"], -L["win_rate"]))   # ชนะมากสุดก่อน, เสมอ→win-rate สูง
        base["tier"] = 1
        base["leaders"] = leaders[:2]
    return base


def _short(name):
    """ย่อชื่อ: ห้างหุ้นส่วนจำกัด→หจก. · บริษัท→บ."""
    return name.replace("ห้างหุ้นส่วนจำกัด", "หจก.").replace("บริษัท", "บ.").strip()


def field_lines(fr: dict, budget_now, scope_label="") -> list:
    """บรรทัดการ์ดเจ้าตลาด (ใครชนะ scope นี้บ่อย + ลดเฉลี่ย). [] ถ้า tier0/ไม่มี leader/ไม่มี budget.
    scope_label = ป้ายบอก scope เช่น ' (ต.นาทม)' / ' (อ.นาทม)'."""
    if not fr or fr.get("tier", 0) == 0 or not fr.get("leaders") or not budget_now:
        return []
    b = float(budget_now)
    lines = [f"🏆 เจ้าตลาดหมวดงานนี้{scope_label}:"]
    for ld in fr["leaders"]:
        wd = ld["win_disc_med"]
        disc_txt = f" · ลดเฉลี่ย ~{wd:.0f}%" if wd is not None else ""
        lines.append(f"   • {_short(ld['name'])} — ชนะ {ld['win_rate'] * 100:.0f}% "
                     f"({ld['wins']}/{ld['appears']} งาน){disc_txt}")
    # ต้องสู้กับเจ้าตลาดที่ "ลดลึกสุด" (ไม่ใช่คนชนะเยอะสุด) — ลึกสุดคือเพดานที่ต้องแซง
    deepest = max((ld["win_disc_med"] for ld in fr["leaders"] if ld["win_disc_med"] is not None),
                  default=None)
    if deepest is not None:
        price = round(b * (1 - deepest / 100.0))
        lines.append(f"   💡 เจ้าตลาดลดได้ถึง ~{deepest:.0f}% (≈{price:,.0f}) — ต้องลดลึกกว่านี้ถึงชนะ")
    return lines


def _field_auctions(conn, province, tokens, subdistrict=None, district=None, project_ids=None) -> list:
    """full-field auctions ของ scope จาก bid_results JOIN cgd_winners(budget).
    project_ids != None → ดึงเฉพาะ id ชุดนั้น (population เดียวกับที่ price ใช้ — เลขตรงกัน).
    project_ids = None → query ตาม scope (province + tokens + ตำบล/อำเภอ จากชื่องาน).
    คืน [ [(bidder_name, disc_pct, is_winner)] ] · ตัด outlier disc นอก [0,DISC_MAX] · graceful []."""
    if project_ids is not None:
        # invariant: caller (predict) ส่ง id จาก used_rows ที่ _fetch กรอง proc_type/subtype/year แล้ว
        ids = list(dict.fromkeys(project_ids))   # dedupe รักษาลำดับ
        if not ids:
            return []
        where = [f"b.project_id IN ({','.join('?' for _ in ids)})", "cw.budget>0"]
        params = list(ids)
    else:
        pt = ",".join("?" for _ in COMPETITIVE_SET)
        like = " OR ".join("cw.project_name LIKE ?" for _ in tokens)
        where = ["cw.province=?", f"cw.proc_type IN ({pt})", f"({like})", "cw.budget>0"]
        params = [province, *COMPETITIVE_SET] + [f"%{t}%" for t in tokens]
        if subdistrict is not None:              # geocode column เพี้ยน → match จากชื่องาน (เหมือน competitor_trend)
            where.append("(cw.project_name LIKE ? OR cw.project_name LIKE ?)")
            params += [f"%ตำบล{subdistrict}%", f"%ต.{subdistrict}%"]
        if district is not None:
            where.append("(cw.project_name LIKE ? OR cw.project_name LIKE ?)")
            params += [f"%อำเภอ{district}%", f"%อ.{district}%"]
    sql = ("SELECT b.project_id, b.bidder_name, b.price_proposal, b.price_agree, b.is_winner, cw.budget "
           "FROM bid_results b JOIN cgd_winners cw ON cw.project_id=b.project_id "
           "WHERE " + " AND ".join(where))
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.DatabaseError:          # missing table/locked/corrupt → graceful (ไม่ทำการ์ดพัง)
        return []
    byp = defaultdict(list)
    for pid, name, pp, pa, isw, budget in rows:
        bid = None
        for x in (pp, pa):                        # sealed bid = proposal (winner ใช้ agree ถ้า proposal ว่าง)
            try:
                f = float(x)
                if f > 0:
                    bid = f
                    break
            except (TypeError, ValueError):
                pass
        try:
            bud = float(budget)
        except (TypeError, ValueError):
            bud = 0
        if not bid or bud <= 0:
            continue
        disc = (bud - bid) / bud * 100.0
        if disc < 0 or disc > DISC_MAX:           # ตัด outlier (unit-price เพี้ยน)
            continue
        byp[pid].append((name or "", disc, bool(isw)))
    return list(byp.values())


def field_and_winrate(conn, province, tokens, budget,
                      subdistrict=None, district=None, scope_label="", basis="", project_ids=None):
    """อ่าน _field_auctions รอบเดียว → คืน (winrate_lines [B], field_lines [2B เจ้าตลาด]).
    project_ids = ชุดงานที่ price ใช้ (population เดียวกัน → เลขตรงกัน). graceful ([],[]) ถ้าว่าง.
    จุดเชื่อม predictor — กัน query ซ้ำ."""
    auctions = _field_auctions(conn, province, tokens, subdistrict, district, project_ids=project_ids)
    wl = winrate_lines(winrate_grid(auctions, budget), basis)
    fl = field_lines(analyze_field(auctions), budget, scope_label)
    return wl, fl
