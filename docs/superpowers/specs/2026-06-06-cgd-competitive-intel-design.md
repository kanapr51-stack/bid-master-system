# CGD Competitive Intel ใน D0 Notification — Design Spec

**วันที่:** 2026-06-06 · **สถานะ:** approved (reviewer: กัญจน์, "approved with minor revisions")

## เป้าหมาย
เมื่อแจ้ง "เปิดประมูลแล้ว" (B0→D0, source_stage=`followed_bid_open`) ให้แนบ **ราคาอ้างอิงจากผู้ชนะงานคล้ายในพื้นที่** (จาก `cgd_winners` บน VPS) เพื่อช่วยครอบครัวเข้าใจ **สนามแข่งขัน** ก่อนตัดสินใจยื่น

**Principle:** descriptive ไม่ prescriptive — อธิบาย "ตลาดเป็นยังไง" **ไม่ใช่** "ควรยื่นราคาเท่าไหร่"

## Non-Goals (จงใจไม่ทำในเฟสนี้)
- ❌ แนะนำราคาที่ควรยื่น (bid-price recommendation) — กัน user เข้าใจผิดว่าระบบสั่งให้ยื่นเท่านี้
- ❌ ปุ่ม on-demand / การ์ดแยก — แนบ D0 อัตโนมัติเท่านั้น (MVP)
- ❌ optimize query (LIKE scan) — volume D0 ต่ำ รับได้

## Architecture
โมดูลใหม่ `scripts/cgd_intel.py` (domain แยกจาก notification — กัน spaghetti) + wiring 1 จุดใน `Sebastian_LINE_Sender.format_notification`.

```
format_notification(source_stage="followed_bid_open")
  └─ try: intel_lines(province, project_name) → แทรกก่อนบรรทัด 🔑
     except: [] (intel = value-add เท่านั้น — ห้ามทำ D0 notification พัง)
```

## Components — `scripts/cgd_intel.py`

### `match_keywords(project_name) -> list[str]`
คืน work-type tokens ที่ปรากฏในชื่องาน โดย reuse vocab จาก `config/matching_preferences.json["keywords"]` (vocab เดียวกับ job_matcher — consistency). ไม่ซ้ำ token.

### `query_similar(province, tokens, min_overlap, conn=None) -> list[dict]`
- query `cgd_winners` WHERE `province=?` AND ชื่อ LIKE ANY token (candidate fetch) AND `win_price > 0`
- filter ใน Python: เก็บ row ที่ชื่อมี **≥ min_overlap** ของ tokens (overlap count)
- คืน list[dict] (project_name, winner, win_price, discount_pct)
- `conn` inject ได้ (test); default = `Sebastian_Customer_DB.get_connection()`

### `compute_stats(rows) -> dict`
- `count` = len(rows)
- `avg_discount` = mean ของ `discount_pct` ที่ไม่ null (อาจ None ถ้าไม่มี valid)
- `price_lo`, `price_hi` = percentile 10 / 90 ของ `win_price` (ตัด outlier)
- `top_winners` = `Counter(winner).most_common(3)` → list[(name, count)]

### `intel_lines(province, project_name, min_count=10) -> list[str]`
orchestrate + format. logic:
```
tokens = match_keywords(project_name)
if not tokens: return []                       # นิยาม "คล้าย" ไม่ได้ → omit
if len(tokens) >= 2:
    rows = query_similar(province, tokens, min_overlap=2)
    if len(rows) < min_count:                  # ข้อมูลไม่พอ → fallback กว้างขึ้น
        rows = query_similar(province, tokens, min_overlap=1)
else:
    rows = query_similar(province, tokens, min_overlap=1)   # งานมี token เดียว
if len(rows) < min_count: return []            # ยังไม่ถึง 10 → omit (กัน stat หลอก)
stats = compute_stats(rows)
return [format lines ...]
```

**min_count=10:** ข้อมูล 617K rows / 2 จว. / 10 ปี → work-type ทั่วไปถึง 10 ง่าย. ถ้าไม่ถึง = ข้อมูลน้อยเกินจะเชื่อ avg → omit section ทั้งหมด (ไม่โชว์ครึ่งๆ)

### output format (LINE text — แนบใน D0 card)
```
💡 ราคาอ้างอิง (งานถนนในนครพนม)
📊 จาก 142 งานย้อนหลัง
📉 ชนะเฉลี่ยต่ำกว่าราคากลาง 8.3%
💵 ช่วงราคาชนะ 0.9–2.4 ลบ.
🏆 ผู้ชนะบ่อย:
  • หจก.อุบลรัตน์ (12)
  • หจก.อชิรญา (8)
  • หจก.X (5)
```
- หัวข้อระบุ work-type หลัก (token แรก) + จังหวัด
- `avg_discount` None → ข้าม บรรทัด 📉
- ช่วงราคาแปลงเป็น "ลบ." (ล้านบาท) 1 ตำแหน่ง

## Wiring — `Sebastian_LINE_Sender.format_notification`
แทรกก่อน `lines.append(f"\n🔑 {project_id}")` เฉพาะเมื่อ `source_stage == "followed_bid_open"`:
```python
if source_stage == "followed_bid_open":
    try:
        import cgd_intel
        il = cgd_intel.intel_lines(province, project_name)
        if il:
            lines.append("━━━━━━━━━━━━━")
            lines.extend(il)
    except Exception:
        pass   # intel = value-add; ห้ามทำ notification พัง
```

## Edge / Safety
- table `cgd_winners` หาย/ว่าง → query คืน [] → omit เงียบ
- province ว่าง / project_name ว่าง → tokens ว่าง → omit
- ทุก error ใน intel ถูก swallow ที่จุด wiring → D0 notification ส่งเสมอ
- query บน VPS (`cgd_winners` มี idx province) — D0 volume ต่ำ (ไม่กี่งาน/วัน) → LIKE scan รับได้

## Testing (TDD) — `scripts/test_cgd_intel.py`
1. `match_keywords("ก่อสร้างถนน คสล.")` ⊇ {ถนน, คสล} ; ชื่อไม่มี work-type → []
2. `query_similar` (inject conn + fixture cgd_winners): filter province + min_overlap (≥2 ตัด งาน token เดียว, ≥1 รับ)
3. `compute_stats`: count/avg_discount/price_lo-hi/top_winners(+count) ถูกต้อง
4. `intel_lines` < min_count → [] ; ≥ min_count → บรรทัดตาม format ; fallback 1-token เมื่อ 2-token ไม่พอ
5. graceful: cgd_winners ไม่มี table → [] (ไม่ throw)

## Future (ยังไม่ทำ)
- **discount median + p25–p75** แทน avg (median แข็งแรงกว่า, outlier-resistant) → "📉 ส่วนลดที่พบบ่อย 6–9%". ทำได้แทบฟรี (sort ชุดเดียวกับ price range) — flip ได้เมื่อกัญจน์ตัดสิน
- เทียบงบงานปัจจุบัน vs ช่วงราคาชนะ
- on-demand button / competitive intel เต็มรูป (รายชื่อคู่แข่งทั้งหมด)

## Rollback
ลบ block wiring ใน `format_notification` (intel แยกโมดูล ไม่กระทบ flow อื่น). `cgd_intel.py` ลบได้อิสระ
