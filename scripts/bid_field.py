"""bid_field.py — "เจ้าตลาด" intel จาก full-field bids (2B). ใครชนะ scope นี้บ่อย + ลดเฉลี่ยเท่าไหร่.
v2 pivot (evidence 2026-06-14): landslide หายาก (5-10%/scope) แต่มีเจ้าตลาดชัด (ชนะ 48-83% ชิดๆ)
→ จับด้วย win-frequency ไม่ใช่ landslide-gap. graceful gate. ดู spec 2026-06-14-dominant-detection-2b."""
import sqlite3, sys, os, math, logging, json, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from cgd_intel import COMPETITIVE_SET, recency_weight

_log = logging.getLogger(__name__)

MIN_AUCTIONS = 5        # scope ต้องมี ≥ นี้ ถึงวิเคราะห์
MIN_APPEAR = 5          # บริษัทต้องลง ≥ นี้ ถึงนับเป็นเจ้าตลาด (ตัดฟลุ๊ค ลง1-2ชนะหมด)
LEADER_WIN_RATE = 0.40  # ชนะ ≥ 40% ของที่ลง (สุ่ม ~17% ที่ 5.9 ราย → 40% = เด่นจริง)
DISC_MAX = 60.0         # ตัด outlier disc (unit-price เพี้ยน)
ESS_FLOOR = 6          # effective sample (weighted) ขั้นต่ำ — bootstrap (ขยับ 8/10 เมื่อ backfill โต = B″)
MIN_N_AUCTIONS = 3     # local auctions ขั้นต่ำที่จะเชื่อ n centering (2 → variance ไร้ความหมาย)
MIN_OWN_BIDS = 5       # จำนวนแถวดิบขั้นต่ำต่อชั้น ก่อนเชื่อประวัติบริษัทเอง (gate นับดิบ ไม่ใช่ ESS — spec §4.2)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


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


def _center_stats(auctions) -> dict:
    """centering math (สกัดจาก _evaluate_winrate): mean/sd จำนวนผู้ยื่น → ns (1..max จริง) + k_mid.
    auctions = [[(name,disc,is_winner[,fy])]] · auction <2 ผู้ยื่นถูกตัด.
    ว่าง → {n:0, n_mean:0, n_sd:0, ns:[], k_mid:None}."""
    sizes = [len(a) for a in auctions if len(a) >= 2]
    n = len(sizes)
    if n == 0:
        return {"n": 0, "n_mean": 0.0, "n_sd": 0.0, "ns": [], "k_mid": None}
    n_mean = sum(sizes) / n
    var = sum((s - n_mean) ** 2 for s in sizes) / (n - 1) if n > 1 else 0.0
    n_sd = math.sqrt(var)
    ns = [1] + list(range(2, max(sizes) + 1))     # ladder เต็ม N=1..max ที่เคยเกิดจริง (เดิม 3 จุด mean±SD)
    k_mid = min(max(2, round(n_mean)), max(sizes))
    return {"n": n, "n_mean": n_mean, "n_sd": n_sd, "ns": ns, "k_mid": k_mid}


def _monitor_path() -> str:
    d = os.environ.get("BMS_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "data")
    return os.path.join(d, "winrate_center_monitor.ndjson")


def _log_center_breadcrumb(local_auc, amphoe_auc, province_auc, grid, conf, basis="") -> None:
    """observe-only: เมื่อ ladder ผ่อน (conf!=None) บันทึกเทียบ center stats 3 scope (local/อำเภอ/จังหวัด)
    ลง ndjson — สะสม evidence ว่า B″ (center บนอำเภอแทนจังหวัด) เปลี่ยนตารางจริงพอจะคุ้มไหม.
    exception-safe: ทุก error เป็น no-op (ห้ามทำการ์ดพัง). ไม่แตะ grid/conf/output."""
    try:
        if not grid or conf is None:
            return
        cl, ca, cp = (_center_stats(local_auc or []), _center_stats(amphoe_auc or []),
                      _center_stats(province_auc or []))
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "basis": basis, "conf": conf[1],
            "n_local": cl["n"], "n_amphoe": ca["n"], "n_province": cp["n"],
            "mean_local": round(cl["n_mean"], 2), "mean_amphoe": round(ca["n_mean"], 2),
            "mean_province": round(cp["n_mean"], 2),
            "kmid_amphoe": ca["k_mid"], "kmid_province": cp["k_mid"], "kmid_chosen": grid["k_mid"],
            "amphoe_eligible": ca["n"] >= MIN_N_AUCTIONS,
            "delta_mean": round(abs(cp["n_mean"] - ca["n_mean"]), 2),
        }
        with open(_monitor_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        _log.debug("center breadcrumb skip", exc_info=True)


def _evaluate_winrate(auctions, budget, local_auctions=None, targets=(75, 50, 25)):
    """source-of-truth: gate + ESS + weighted quantile + local-n centering.
    คืน dict เสมอ — ok=True พร้อม grid fields, หรือ ok=False พร้อม fail_reason
    (AUCTIONS/ESS/BOTH/BUDGET/PRICE_COLLAPSE). auctions/local_auctions = [[(name,disc,is_winner[,fy])]].
    local_auctions = scope แคบสุด (≥MIN_N_AUCTIONS) สำหรับ center คอลัมน์ (None → ใช้ auctions)."""
    auctions = [a for a in auctions if len(a) >= 2]
    n_auctions = len(auctions)
    try:
        bud = float(budget)
    except (TypeError, ValueError):
        bud = 0
    if bud <= 0:
        return {"ok": False, "fail_reason": "BUDGET", "ess": 0.0}
    pairs = []                                          # (disc, recency_weight)
    for a in auctions:
        for bid in a:
            fy = bid[3] if len(bid) > 3 else None
            pairs.append((bid[1], recency_weight(fy)))
    ess = 0.0
    if pairs:
        ess = sum(w for _d, w in pairs)   # Σw (current-year bid = weight 1.0) — ประมาณ n ที่ปรับความสด
    fail = []
    if n_auctions < MIN_AUCTIONS:
        fail.append("AUCTIONS")
    if ess < ESS_FLOOR:
        fail.append("ESS")
    if fail:
        reason = "BOTH" if len(fail) == 2 else fail[0]
        return {"ok": False, "fail_reason": reason, "ess": ess}
    # n centering: ใช้ local ถ้าหนาพอ ไม่งั้น F-scope
    src = [a for a in (local_auctions or []) if len(a) >= 2]
    if len(src) < MIN_N_AUCTIONS:
        src = auctions
    cs = _center_stats(src)
    n_mean, n_sd, ns, k_mid = cs["n_mean"], cs["n_sd"], cs["ns"], cs["k_mid"]
    rows, seen_price = [], set()
    for t in targets:
        tf = t / 100.0
        disc = _weighted_quantile(pairs, tf ** (1.0 / k_mid))    # ราคา = inverse weighted-CDF
        price = round(bud * (1 - disc / 100.0))
        if price in seen_price:
            continue
        seen_price.add(price)
        rows.append((price, [100 if k == 1 else round(tf ** (k / k_mid) * 100) for k in ns]))
    if len(rows) < 2:
        return {"ok": False, "fail_reason": "PRICE_COLLAPSE", "ess": ess}
    rows.sort()
    return {"ok": True, "fail_reason": "OK", "ns": ns, "rows": rows,
            "n_mean": n_mean, "n_sd": n_sd, "n_auctions": n_auctions,
            "n_bids": len(pairs), "ess": ess, "k_mid": k_mid, "budget": bud}


def winrate_grid(auctions, budget, local_auctions=None, targets=(75, 50, 25)):
    """ตาราง win% conditional (B′). wrapper ของ _evaluate_winrate — คง contract dict|None.
    None เมื่อ gate ไม่ผ่าน (ดู fail_reason ใน _evaluate_winrate)."""
    g = _evaluate_winrate(auctions, budget, local_auctions, targets)
    return g if g.get("ok") else None


def winrate_lines(grid, conf=None, price_basis="") -> list:
    """render ตาราง win% (pure). [] ถ้า grid None.
    conf=None → 🟢 local (ไม่มี disclaimer). conf=(emoji, scope_word) → assisted:
    เพิ่มป้าย scope + ⚠️ ย้ำว่าราคาด้านบนยังอิง price_basis (กันเข้าใจผิดว่าราคาตาราง=ราคาแนะนำ)."""
    if not grid:
        return []
    ns, rows = grid["ns"], grid["rows"]
    lines = [f"💵 โอกาสชนะตามจำนวนผู้ยื่น (งบ {grid['budget']:,.0f})"]
    lines.append("   ผู้ยื่น →   " + "  ".join(f"{k}ราย".rjust(6) for k in ns))
    for price, ws in rows:
        cells = "  ".join(f"{w}%".rjust(6) for w in ws)
        lines.append(f"   {price:>10,.0f}  {cells}")
    sd_txt = f" (±{round(grid['n_sd'])})" if len(ns) > 1 else ""
    lines.append(f"   📊 สนามนี้เฉลี่ย {round(grid['n_mean'])} ผู้ยื่น{sd_txt}")
    lines.append(f"   📈 จาก {grid['n_auctions']} งานที่มีข้อมูลผู้ยื่นครบ · {grid['n_bids']} ราย")
    if conf:
        emoji, scope_word = conf
        lines.append(f"   {emoji} โอกาส% อิง{scope_word} (พื้นที่นี้ข้อมูลบาง)")
        if price_basis:
            lines.append(f"   ⚠️ ราคาด้านบนยังอิง{price_basis} — ตารางนี้บอกเฉพาะ \"โอกาสชนะ%\"")
    lines.append("   * คอลัมน์ตรงค่าเฉลี่ย = เป้า 75/50/25 · ยิ่งผู้ยื่นเยอะ โอกาสยิ่งต่ำ")
    return lines


def _winner_idx(auction):
    """index ผู้ชนะ: is_winner ก่อน, fallback disc สูงสุด."""
    for i, t in enumerate(auction):
        if t[2]:
            return i
    return max(range(len(auction)), key=lambda i: auction[i][1])


def analyze_field(auctions: list) -> dict:
    """market-leader detection (win-frequency). auctions = [ [(name, disc_pct, is_winner, fiscal_year)] ].
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
        wname, wdisc = a[wi][0], a[wi][1]
        seen = set()
        for t in a:
            nm = t[0]
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
    คืน [ [(bidder_name, disc_pct, is_winner, fiscal_year)] ] · ตัด outlier disc นอก [0,DISC_MAX] · graceful []."""
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
    sql = ("SELECT b.project_id, b.bidder_name, b.price_proposal, b.price_agree, b.is_winner, "
           "cw.budget, cw.fiscal_year "
           "FROM bid_results b JOIN cgd_winners cw ON cw.project_id=b.project_id "
           "WHERE " + " AND ".join(where))
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.DatabaseError:          # missing table/locked/corrupt → graceful (ไม่ทำการ์ดพัง)
        return []
    byp = defaultdict(list)
    for pid, name, pp, pa, isw, budget, fy in rows:
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
        try:
            fy_int = int(fy) if fy is not None else None
        except (TypeError, ValueError):
            fy_int = None
        byp[pid].append((name or "", disc, bool(isw), fy_int))
    return list(byp.values())


_CONF = {0: None, 1: ("🟡", "อำเภอ"), 2: ("🟠", "จังหวัด")}   # ระยะผ่อนจาก price scope


def _scope_ids(conn, province, tokens, cf, subdistrict=None, district=None):
    """project_ids ของ scope (คง cf จัดเต็มผ่าน _fetch_scope — population เดียวกับราคา). [] ถ้าว่าง/error."""
    try:
        from cgd_intel import _fetch_scope
        rows, _old = _fetch_scope(conn, province, tokens,
                                  subdistrict=subdistrict, district=district, **(cf or {}))
        return [r["project_id"] for r in rows if r.get("project_id")]
    except Exception:                                   # graceful แต่ surface (กัน silent swallow)
        _log.warning("_scope_ids failed (district=%s) → []", district, exc_info=True)
        return []


def field_and_winrate(conn, province, tokens, budget, subdistrict=None, district=None,
                      scope_label="", basis="", project_ids=None, cf=None, amphoe=None):
    """orchestrator: อ่าน price-scope auctions → ลองทำตาราง → ผ่อน ladder (อำเภอ→จังหวัด)
    จน gate ผ่าน. คืน (grid|None, field_lines[2B], conf). conf=None(🟢)/('🟡','อำเภอ')/('🟠','จังหวัด').
    grid = dict จาก _evaluate_winrate (ns/rows/n_mean/n_sd/n_auctions/n_bids/ess/k_mid/budget) — caller render เอง.
    n centering = price-scope auctions (local) เสมอ. 2B (field_lines) อิง price-scope."""
    if project_ids is not None:
        local_auc = _field_auctions(conn, province, tokens, project_ids=project_ids)
    else:
        local_auc = _field_auctions(conn, province, tokens, subdistrict, district)
    attempts = [local_auc]                                  # 0 = price scope (🟢)
    if amphoe and cf is not None:                           # ผ่อนได้เฉพาะตอนรู้ amphoe + cf
        attempts.append(_field_auctions(conn, province, tokens,
                        project_ids=_scope_ids(conn, province, tokens, cf, district=amphoe)))
        attempts.append(_field_auctions(conn, province, tokens,
                        project_ids=_scope_ids(conn, province, tokens, cf)))
    grid, conf, reason = None, None, "OK"
    for i, auc_ in enumerate(attempts):
        ev = _evaluate_winrate(auc_, budget, local_auctions=local_auc)
        reason = ev["fail_reason"]
        if ev.get("ok"):
            grid, conf = ev, _CONF.get(i)
            break
    _log.info("winrate basis=%s conf=%s ess=%.1f k_local=%s fail_reason=%s",
              basis, ("local" if conf is None else conf[1]) if grid else "none",
              grid["ess"] if grid else 0.0, grid["k_mid"] if grid else None, reason)
    # B″ offline monitor (observe-only) — เมื่อผ่อนถึงอำเภอ/จังหวัด สะสม center-error เทียบ scope
    if grid and conf is not None:
        _log_center_breadcrumb(local_auc, attempts[1] if len(attempts) > 1 else [],
                               attempts[2] if len(attempts) > 2 else [], grid, conf, basis)
    fl = field_lines(analyze_field(local_auc), budget, scope_label)
    return grid, fl, conf


def gates_winrate(probs):
    """Gates (1967) combine: P_win = 1/(1+Σ(1−Pi)/Pi). แก้ Friedman collapse (∏Pi → 0 เมื่อคนเยอะ).
    probs=[Pi] (โอกาสเราชนะคู่แข่งแต่ละราย, ควร clamp (0,1) มาแล้ว). ตัด None ทิ้ง. ว่าง → None."""
    ps = [p for p in probs if p is not None]
    if not ps:
        return None
    s = sum((1.0 - p) / p for p in ps)
    return 1.0 / (1.0 + s)


def p_beat(dist, my_discount):
    """โอกาสเราชนะคู่แข่ง 1 ราย = สัดส่วนถ่วงน้ำหนักของ bids ที่ลด 'ตื้นกว่า' เรา (ราคาเขาสูงกว่า = เราชนะ).
    dist=[(discount, weight)]. clamp [0.05,0.95] (กันมั่นใจเกินจริง). น้ำหนักรวม≤0 → None."""
    tot = sum(w for _d, w in dist)
    if tot <= 0:
        return None
    below = sum(w for d, w in dist if d < my_discount)
    return max(0.05, min(0.95, below / tot))
