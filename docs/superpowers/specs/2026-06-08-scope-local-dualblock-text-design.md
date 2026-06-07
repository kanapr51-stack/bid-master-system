# Scope-Local Competitor Stats + Dual-Block + Plain-Text Delivery — Design Spec

**วันที่:** 2026-06-08 · **สถานะ:** APPROVED (brainstorm กับกัญจน์, autonomous build no-checkpoint) · ต่อยอด price-prediction + moi-location

## เป้าหมาย (3 เรื่องรวม)
1. **สถิติคู่แข่ง scope-local** — แต่ละบริษัทนับเฉพาะงานใน scope นั้น (ตำบล/อำเภอ) + work-type นี้ **ไม่เอาประวัติทั้งบริษัท** (กัญจน์สั่ง — แก้ความสับสน per-company% ≠ area%)
2. **Dual-block** — โชว์ระดับตำบล**เสมอ** + อำเภอ**คู่กันเมื่อตำบลน้อย** ("บอกให้หมด"). คาดราคา**อิงตำบล**
3. **ส่งเป็น text ธรรมดา** — followed_bid_open ส่ง LINE text message (ไม่ใช่ flex card) → จบใน 1 ข้อความ ไม่ truncate ไม่มีปุ่ม (งาน followed แล้ว ไม่ต้องมี ⭐)

**คง 3 ปี (FY2566-68).** Data finding: ต.โพธิ์หมากแข้ง งานถนน 3 ปี = 36 งาน แต่ 33 จ้างตรง (92%) → เหลือ 3 e-bidding = สนามแข่งจริง (ตรง [[project_cgd_market_insight]] → ตำบลงานแข่งน้อยโดยธรรมชาติ → dual-block จำเป็น)

## พฤติกรรม
```
resolve_location → (tambon, amphoe)
ในตำบล block (เสมอ): _fetch(subdistrict=tambon, district=amphoe) → คู่แข่ง + ส่วนลด (scope-local)
   ถ้าตำบล 0 งาน → "ยังไม่มีงานประเภทนี้ในตำบล"
ถ้า tambon games < TAMBON_MIN(5):
   ในอำเภอ block: _fetch(district=amphoe) → คู่แข่ง + ส่วนลด (scope-local อำเภอ)
คาดราคา: อิง area p25/p75 ของ**ตำบล** (ถ้า ≥1 งาน) · ตำบล 0 → อิงอำเภอ (บอกระดับ)
ถ้า resolve ไม่ได้ amphoe → block เดียว (province) เหมือนเดิม
```

## Output (text ธรรมดา, ตัวอย่างจริง 69059075454)
```
💡 ราคาอ้างอิง (งานถนน ต.โพธิ์หมากแข้ง อ.บึงโขงหลง)

🏘 ในตำบลโพธิ์หมากแข้ง — 3 งาน 🔴 ข้อมูลน้อย
  • หจก.ว่องเจริญ··· · 1 งาน · ลด 36%
  • หจก.เดชา··· · 1 งาน · ลด 26%
  • หจก.ศิรประภา··· · 1 งาน · ลด 21%
  📊 ส่วนลดในตำบล 21–36%

🏙 ในอำเภอบึงโขงหลง — 11 งาน 🟡
  • หจก.เดชา··· · 3 งาน · ลด 18%
  • หจก.ยศประทาน··· · 2 งาน · ลด 42%
  • หจก.ชัยฤทธิ์··· · 1 งาน · ลด 41%
  📊 ส่วนลดในอำเภอ 0–42%

💵 คาดราคาที่จะชนะ (ราคากลาง 1.0 ลบ.):
   • อิงตำบล ลด 21–36% → ชนะราว 0.65–0.80 ลบ.
   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ
```

## Components — `cgd_intel.py`
- `_company_stats_from_rows(rows, winner)` → {games, median, p25, p75} จาก rows (scope-local, ไม่ query broad). games<MIN_GAMES_FOR_IQR(3) → ไม่มี IQR
- `_scope_block(rows, label) -> (lines, p25, p75, n)` — header + top-N คู่แข่ง + ส่วนลด + ป้าย conf
- `intel_context(province, project_name, dept_name, project_id, budget=0, conn) -> dict|None` — orchestrate dual-block + prediction. คืน `{lines, prediction}` (prediction dict สำหรับ save_prediction). None ถ้าไม่มี work-type/คู่แข่งเลย
- `predict_winning_price` reuse (รับ p25/p75 ของ scope ที่เลือก = ตำบล)
- **ลบ** `_fetch_winner` + `company_stats` (broad) — เลิกใช้
- config: `TAMBON_MIN = 5` (ตำบล < นี้ → โชว์อำเภอด้วย)

## Delivery — `Sebastian_LINE_Sender.py`
- followed_bid_open: ส่ง **text message** (send_line_text/push text) แทน flex card. format_notification คืน text เดิม + ctx["lines"] (intel+prediction) + store prediction
- verify: sender มี text-send path (ถ้าไม่มี เพิ่ม send_line_text ผ่าน LINE push API type=text)

## Edge / Safety
- ตำบล 0 + อำเภอมี → โชว์ "ตำบล: ยังไม่มี" + อำเภอ block + คาดราคาอิงอำเภอ
- ไม่มีคู่แข่งเลยทั้ง 2 scope → omit intel (text ปกติของ D0)
- ทุก path try/except — intel พังไม่ทำ notification ล่ม
- prediction store เฉพาะเมื่อคำนวณได้ (idempotent)

## Testing (TDD)
1. `_company_stats_from_rows`: นับเฉพาะ winner ใน rows, games<3→ไม่มี IQR
2. `_scope_block`: header+คู่แข่ง+ส่วนลด+conf, 0 rows→ข้อความ "ยังไม่มี"
3. `intel_context` dual: ตำบลพอ(≥5)→block เดียว · ตำบลน้อย→ตำบล+อำเภอ 2 block · ตำบล 0→ตำบล"ยังไม่มี"+อำเภอ · คาดราคาอิงตำบล · คืน prediction
4. delivery: followed_bid_open ส่ง text (mock send) ไม่ใช่ flex
5. graceful: ไม่มีคู่แข่ง→omit

## Rollback
revert intel_context (กลับ single-block broad) + delivery (flex). additive ทั้งหมด
