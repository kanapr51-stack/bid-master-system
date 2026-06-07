# Price Prediction + Closed-Loop Verify (Credibility Engine) — Design Spec

**วันที่:** 2026-06-07 · **สถานะ:** APPROVED (brainstorm กับกัญจน์) · ต่อยอด [`tambon-competitor-intel`](2026-06-07-tambon-competitor-intel-design.md) + [`moi-location-disambiguation`](2026-06-07-moi-location-disambiguation-design.md)

## เป้าหมาย
ให้ Sebastian **คาดช่วงราคาที่จะชนะ** ตอนงานเปิดประมูล (D0) → **เทียบกับราคาชนะจริง** ตอนประกาศผล (W0) → แจ้งผล + สะสม accuracy. คาดตรงสะสม = **credibility ของสถิติ Sebastian เพิ่มขึ้น** (ไม่ใช่พูดลอยๆ)

**Principle (กัญจน์ย้ำ):** ราคาที่คาด = **prediction เชิงสถิติ ไม่ใช่คำสั่ง** — พ่อแม่คำนวณต้นทุน/ตัดสินใจเองอยู่ดี. การ์ดต้อง frame เป็น "คาดการณ์ + โปรดคำนวณต้นทุนจริงประกอบ" ไม่ใช่ "ต้องยื่นเท่านี้". คุณค่าหลัก = **วัดความแม่น → สร้างความน่าเชื่อถือของ data** (ดู [[project_value_principle]])

## Scope / Phasing
- **Sub-project 1 (spec นี้):** Price Prediction + Closed-Loop Verify
- **Sub-project 2 (defer):** Calibration & error-analysis (3 ปีเก่าไป? วัสดุแกว่ง?) — **ต้องรอ accuracy data จาก SP1 ก่อน** (dependency บังคับลำดับ)

## Non-Goals
- ❌ สั่งราคาที่ "ต้องยื่น" (เป็น prediction ไม่ใช่ command)
- ❌ คาดราคาเมื่อข้อมูลไม่พอ (omit ดีกว่าเดามั่ว — ตาม principle เดิม)
- ❌ retrain/calibrate ใน SP1 (= SP2)

## Infra ที่มีอยู่แล้ว (reuse)
- `bid_results` (v118): ผู้ยื่นทุกราย + `price_proposal` + `price_agree` + `is_winner` → ราคาชนะจริง = `price_agree` ของ row `is_winner=1`
- `Sebastian_Winner_Poller.py`: poll ผลงานที่ติดตาม → `record_bid_results` + enqueue `followed_winner` → **จุดเสียบ closed-loop**
- competitor stats + resolve_location (จาก 2 feature ก่อน) → ใช้คำนวณ prediction

## Data flow
```
D0 (followed_bid_open enqueue): predict_winning_price() → เก็บ price_predictions (idempotent) + โชว์การ์ด
        ↓ ... รอประกาศผล ...
W0 (Winner_Poller เจอผล): actual = price_agree ผู้ชนะ
        ↓ lookup price_predictions → in-range? + error% → verdict
        ↓ แทรกการ์ด followed_winner ("คาด X–Y / ชนะจริง Z · ✅ตรง คลาด N%")
        ↓ UPDATE price_predictions (actual/in_range/error_pct/verified_at)
        → credibility metric สะสม
```

## Components

### `predict_winning_price(budget, area_stats, top_competitor, conn=...) -> dict | None` (cgd_intel)
- input: ราคากลาง `B` + competitor stats แถบที่ resolve ได้ (reuse จาก intel_lines)
- **ช่วงตลาด:** area discount p25/p75 → ราคา `[B×(1−p75/100), B×(1−p25/100)]`
- **เจ้าตัวเต็ง:** median discount ของเจ้า active สุด `d_top` → `B×(1−d_top/100)`
- คืน `{area_disc_lo, area_disc_hi, area_price_lo, area_price_hi, top_name, top_disc, top_price}` · ข้อมูลไม่พอ/ไม่มี budget → `None`
- **โชว์ % ก่อน → ราคา** (transparency: ผู้อ่านเห็นที่มา ไม่ลอย)

### การ์ด D0 (ต่อจาก competitor intel เดิม)
```
📊 ภาพรวม: งานแบบนี้แถบนี้มักลด 8–15% จากราคากลาง
💵 คาดราคาที่จะชนะ (ราคากลาง 2.1 ลบ.):
   • ตลาดแถบนี้ลด 8–15% → ชนะราว 1.8–1.9 ลบ.
   • เจ้าตัวเต็ง (ศิรประภา) มักลด ~11% → ~1.87 ลบ.
   * ประเมินจากสถิติ โปรดคำนวณต้นทุนจริงประกอบ
```

### `price_predictions` table (migrate v122)
`project_id PK · budget · area_disc_lo · area_disc_hi · area_price_lo · area_price_hi · top_name · top_disc · top_price · predicted_at · actual_price · in_range · error_pct · verified_at`
- D0: INSERT OR IGNORE (เก็บคำทำนายแรกที่โชว์ — idempotent กัน re-render เปลี่ยนค่า)
- W0: UPDATE actual_price/in_range/error_pct/verified_at

### Closed-loop ใน Winner_Poller
ตอนเจอผล (ก่อน/พร้อม enqueue followed_winner):
- `actual` = price_agree ผู้ชนะ (จาก res["bidders"]) แปลงเป็น float
- lookup price_predictions(project_id); ถ้ามี + actual parse ได้:
  - `in_range = area_price_lo ≤ actual ≤ area_price_hi`
  - `error_pct = round(abs(actual − mid)/actual×100)` (mid = กลางช่วงตลาด)
  - UPDATE row
- ส่ง verdict ไปให้การ์ด followed_winner แสดง (ผ่าน field ใน enqueue payload หรือ render อ่าน price_predictions)

### การ์ด W0 (followed_winner — เพิ่มบรรทัดเทียบ)
```
🏆 ผู้ชนะ: หจก.X · 1.95 ลบ.
🎯 Sebastian คาด 1.8–1.9 ลบ. → ✅ ตรง (คลาด 3%)
   [หรือ ❌ ไม่ตรง (สูงกว่าคาด 12%) — เก็บไปพัฒนาความแม่น]
```
ถ้าไม่มี prediction เก็บไว้ → การ์ดผู้ชนะออกปกติ (ไม่มีบรรทัดนี้)

### Credibility metric — real-time ทุกครั้งที่มีผล (กัญจน์เลือก)
ใน Winner_Poller หลัง UPDATE price_predictions ของงานนั้น → **คำนวณ running accuracy สะสม** (in-range rate % + mean error% จาก verified ทั้งหมด) → **ส่ง Discord ทันที** พร้อมผลงานนั้น:
```
🎯 ผลทำนาย: 69059xxx (งานถนน อ.บึงโขงหลง)
   คาด 1.8–1.9 / จริง 1.95 → ✅ ตรง (คลาด 3%)
   📊 สะสม: ตรง 7/9 (78%) · คลาดเฉลี่ย 6%
```
- ส่งทุกครั้งที่ closed-loop verify เกิด (real-time, ไม่รอ weekly) → กัญจน์เห็น credibility trend ทันที
- helper `prediction_accuracy_summary(conn) -> dict` (in-range rate + mean error + count) แยกฟังก์ชัน (test ได้) ใช้ทั้ง real-time Discord + on-demand query
- (การ์ด W0 ต่อพ่อ = verdict per-result มีอยู่แล้ว; running stat ส่ง Discord กัญจน์)

## ราคากลาง (budget) source
ใช้จาก notification snapshot (`budget` ที่การ์ด D0 ใช้แสดงอยู่แล้ว). verify แหล่งที่แม่นสุดตอน plan (projects_seen.budget vs getProcurementDetail.budget — อาจ capture จาก resolve เหมือน location)

## Edge / Safety
- ข้อมูล competitor ไม่พอ / ไม่มี budget → predict คืน None → ไม่โชว์ราคาคาด (เหมือน intel omit)
- W0 ไม่มี prediction เก็บไว้ → การ์ดผู้ชนะออกปกติ ไม่มีบรรทัดเทียบ
- actual price parse ไม่ได้ (ราคาเป็น text แปลก) → ข้ามการเทียบ (เก็บ actual=null)
- ทุก path ห่อ try/except — closed-loop พังห้ามทำการ์ด D0/ผู้ชนะพัง
- ⏳ credibility สะสมทีละรอบประมูล (ตอนนี้ bid_results=0 ยังไม่มีงาน awarded) — เป็นธรรมชาติ ไม่ใช่บั๊ก

## Testing (TDD)
1. `predict_winning_price`: range + top จาก budget×discount · ข้อมูลน้อย/ไม่มี budget → None · โชว์ % ถูก
2. in-range verdict + error% (actual ในช่วง→ตรง · นอกช่วง→ไม่ตรง + error ถูก)
3. price_predictions: D0 INSERT idempotent (re-run ไม่เปลี่ยนค่าแรก) · W0 UPDATE actual/verdict
4. Winner_Poller closed-loop: มี prediction→เทียบ+update+verdict ในการ์ด · ไม่มี prediction→การ์ดปกติ · actual parse ไม่ได้→ข้าม
5. `prediction_accuracy_summary`: in-range rate + mean error% + count (+ empty case)
6. graceful: ทุก error swallow ไม่ทำ notification พัง

## Rollback
revert: ลบบรรทัดราคาคาดในการ์ด D0 + closed-loop block ใน Winner_Poller + observe script. price_predictions เป็น table ใหม่ (additive). ไม่กระทบ flow เดิม

## Future (SP2+)
- Calibration: ถ้า error สูงเป็นระบบ → ปรับ window (เน้นปีล่าสุด), เพิ่ม factor ราคาวัสดุ/ฤดูกาล, per-work-type tuning
- โชว์ credibility บนการ์ด ("สถิติ Sebastian แม่น 8/10 รอบล่าสุด") เมื่อ sample พอ
