# Spec: B″ Offline Center-Error Monitor (observe-only)

**วันที่:** 2026-06-16 · **สถานะ:** design → implement (overnight autonomous)
**เกี่ยว:** decision N+141 ([[project_winrate_bprime_coverage_limit]]) — B″ defer, เก็บ offline monitor วัด center error หลายพื้นที่ก่อนตัดสิน

## ปัญหาที่ตอบ

เมื่อ winrate ladder ผ่อนถึง 🟠 จังหวัด เพราะ local full-field < MIN_N_AUCTIONS(3) → `_evaluate_winrate`
center คอลัมน์ (`k_mid`, `n_mean`) fallback ไปใช้ scope ที่ผ่อน (จังหวัด, n≈8-9). แต่ "อำเภอ" (intermediate
scope) อาจให้ center ใกล้ความจริงกว่า (n≈3-4 = จำนวนผู้ยื่นจริงในพื้นที่). B″ candidate = center บน
intermediate scope. **คำถาม: ต่างกันเยอะพอจะคุ้ม implement ไหม?** ต้องวัด evidence หลายพื้นที่ก่อน.

## สิ่งที่ทำ (observe-only — ไม่เปลี่ยน output การ์ด)

ใน `field_and_winrate` หลังได้ `grid`+`conf` แล้ว: ถ้า `conf is not None` (ผ่อน) → เขียน breadcrumb
1 บรรทัดเทียบ center stats ของ 3 scope (local / อำเภอ / จังหวัด) ลง ndjson. **ไม่แตะ grid/conf/lines.**

### helper ใหม่ `_center_stats(auctions) -> dict`
สกัด logic centering เดิม (`_evaluate_winrate` บรรทัด 87-97) → `{n, n_mean, n_sd, ns, k_mid}`.
`_evaluate_winrate` เรียก helper นี้แทน inline (DRY · พฤติกรรมเท่าเดิม — existing test ยืนยัน).
n<1 → graceful `{n:0, ...}`.

### monitor `_log_center_breadcrumb(local_auc, amphoe_auc, province_auc, grid, conf)`
- คำนวณ `_center_stats` ของ 3 scope
- record: `{ts, basis(ผ่าน param), conf(scope_word), n_local, n_amphoe, n_province,
  mean_local, mean_amphoe, mean_province, kmid_amphoe, kmid_province, kmid_chosen(=grid k_mid),
  amphoe_eligible(n_amphoe>=MIN_N_AUCTIONS), delta_mean(|mean_province-mean_amphoe|)}`
- เขียน append ndjson `BMS_DATA_DIR/winrate_center_monitor.ndjson`
- **exception-safe**: ทุก error กลืนเป็น no-op (ห้ามทำการ์ดพัง — เหมือน build_follow_link)

### analysis `scripts/analyze_center_monitor.py`
อ่าน ndjson → สรุป: จำนวน record, %ที่ conf=จังหวัด, %ที่ amphoe_eligible, distribution ของ delta_mean
(median/p90), %ที่ delta_mean≥2 (= อำเภอ center ต่างจากจังหวัด ≥2 ผู้ยื่น = B″ จะเปลี่ยนตารางจริง).

## Success criteria (verifiable)

1. `test_winrate_grid` + `test_bid_field` + `test_cgd_intel` = **ยัง PASS ทั้งหมด** (พิสูจน์ observe-only ไม่ regression)
2. test ใหม่: feed attempts synthetic (local<3, อำเภอ=4, จังหวัด=10) → breadcrumb record มี field ครบ +
   `amphoe_eligible=True` + `delta_mean` = |10-4 center| ถูก + `kmid_chosen`=grid k_mid
3. test: `conf=None` (🟢 local) → **ไม่เขียน breadcrumb** (monitor ทำงานเฉพาะตอนผ่อน)
4. test: monitor exception (เช่น write ไม่ได้) → field_and_winrate ยังคืน (wl, fl, conf) ปกติ
5. `analyze_center_monitor.py` รันกับ ndjson synthetic → output distribution ถูก

## ขอบเขต (ไม่ทำ)
- ❌ ไม่เปลี่ยน centering logic จริง (= B″ เอง, defer)
- ❌ ไม่ deploy/run บน VPS (commit local รอกัญจน์ review+deploy เช้า)
- evidence จริงสะสมหลัง deploy (monitor ทำงานเงียบ) → review distribution ค่อยตัดสิน B″
